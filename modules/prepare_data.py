''' SOILIE 3D
    v.24.04.14
    Written by Mike Cichonski
    With contributions from Tae Bourque and Isil Sanusoglu
    for the Science of Imagination Laboratory
    Carleton University

    File: prepare_data.py
	This file processes all the csv files output by collect_data.py and
	averages/fuzzifies the values of the object triplets.
	It also estimates relative object sizes using the object's
	largest measured diameter (unable to find true volume due
	to incomplete 3d data). Requires output from collect_data.py.'''

import fnmatch
import os
from os.path import join
import sys
import ast
import pickle
import json
import random
import math
from math import sqrt
import numpy as np
import pandas as pd
from itertools import permutations

from modules.timer import *
from modules import progress_bar


def loadObjectSizes():
    '''load object sizes into list'''
    sFile = open(os.path.join(os.getcwd(),"data/object_sizes.csv"),'r')
    sizes = {}
    lines = sFile.readlines()
    sFile.close()
    for line in lines[1:]:
        item = line.split(',')
        sizes[item[0]] = float(item[1])
    return sizes


def gatherTriplets():
    # gather all triplet values into a single file =======================###
    print("Gathering all triplets into single file...")
    timer = startTimer()
    files = []
    for root, dirnames, filenames in os.walk('data'):
        for filename in fnmatch.filter(filenames, '*.csv'):
            files.append(os.path.join(root, filename))

    files = sorted(f for f in files if not (f=='data/object_sizes.csv' or
                   'data/triplets' in f or f=='data/working-combos.csv' or
                   'centroids.csv' in f))
    files.sort(key=len)

    master_df = pd.DataFrame()
    for i, filename in enumerate(files):
        df = pd.read_csv(filename)
        df['objectA'] = df['objectA'].apply(lambda x: x.rsplit('_',1)[0])
        df['objectB'] = df['objectB'].apply(lambda x: x.rsplit('_',1)[0])
        df['objectC'] = df['objectC'].apply(lambda x: x.rsplit('_',1)[0])
        master_df = pd.concat([master_df,df])
        progress_bar.update(i+1,len(files),suffix=filename+'                       ')

    master_df.sort_values(by=list(master_df.columns)).to_csv('./data/triplets.csv', index=False)
    sys.stdout.write("Done! (%s sec.)\n"%str(endTimer(timer))); sys.stdout.flush()


def averageTriplets():

    # average triplet values =======================###
    sys.stdout.write("Averaging triplets..."); sys.stdout.flush()
    timer = startTimer()
    files = []
    for root, dirnames, filenames in os.walk('data'):
        for filename in fnmatch.filter(filenames, '*.csv'):
            files.append(os.path.join(root, filename))
    files = sorted(files)

    averages = {}
    for filename in files:
        if filename=='data/object_sizes.csv' or 'data/triplets' in filename or filename=='data/working-combos.csv' or 'centroids.csv' in filename:
            continue # skip these because they are the output of the current script
        df_trip = pd.read_csv(filename)

        # Column name cleanup - not necessary if original CSV files were saved using pandas
        df_trip.columns = [c.strip() for c in df_trip.columns] # remove extra spaces around names
        df_trip.to_csv(filename,index=False)

        for i, row in df_trip.iterrows():
            objA = row['objectA'].rsplit('_',1)[0]
            objB = row['objectB'].rsplit('_',1)[0]
            objC = row['objectC'].rsplit('_',1)[0]
            triplet = ','.join([objA,objB,objC])
            distAB = float(row['distanceAB'])
            distAC = float(row['distanceAC'])
            distAO = float(row['distanceAO'])
            angBAC = float(row['angleOAB'])
            angOAB = float(row['angleOAC'])
            angOAC = float(row['angleBAC'])
            if triplet not in averages:
                averages[triplet] = [[distAB],[distAC],[distAO],[angBAC],[angOAB],[angOAC],1]
                continue
            averages[triplet][0].append(distAB)
            averages[triplet][1].append(distAC)
            averages[triplet][2].append(distAO)
            averages[triplet][3].append(angBAC)
            averages[triplet][4].append(angOAB)
            averages[triplet][5].append(angOAC)
            averages[triplet][6]+=1

    triplets = {'objectA':[],'objectB':[],'objectC':[],'distanceAB':[],'distanceAC':[],
                'distanceAO':[],'angleBAC':[],'angleOAB':[],'angleOAC':[],'count':[]}

    for triplet, values in averages.items():
        objA, objB, objC = triplet.split(',')
        triplets['objectA'].append(objA)
        triplets['objectB'].append(objB)
        triplets['objectC'].append(objC)
        triplets['distanceAB'].append(sum(values[0])/values[6])
        triplets['distanceAC'].append(sum(values[1])/values[6])
        triplets['distanceAO'].append(sum(values[2])/values[6])
        triplets['angleBAC'].append(sum(values[3])/values[6])
        triplets['angleOAB'].append(sum(values[4])/values[6])
        triplets['angleOAC'].append(sum(values[5])/values[6])
        triplets['count'].append(values[6])

    df_triplets = pd.DataFrame(triplets)
    df_triplets.to_csv('./data/triplets_avg.csv', index=False)

    with open ('data/triplets_avg.pickle','wb') as handle:
        pickle.dump(triplets,handle,protocol=pickle.HIGHEST_PROTOCOL)
    handle.close()

    sys.stdout.write("Done! (%s sec.)\n"%str(endTimer(timer))); sys.stdout.flush()


def approximateObjectSizes():
    # approximate object sizes =============================###

    sys.stdout.write("Approximating object diameters...\n"); sys.stdout.flush()
    timer = startTimer()
    files3D = []
    cenFiles = []
    count = 0
    for root, dirnames, filenames in os.walk('data'):
        for filename in fnmatch.filter(filenames,'*.3d'):
            files3D.append(os.path.join(root,filename))
        for filename in fnmatch.filter(filenames,'*centroids.csv'):
            cenFiles.append(os.path.join(root,filename))

    files3D.sort() # regular in-place sort first
    files3D.sort(key=len) # then sort by filename length, as this correctly sorts number strings alphabetically

    cenFiles.sort()
    cenFiles.sort(key=len)
    cen_dfs = {f:pd.read_csv(f) for f in cenFiles}

    progress_bar.update(0,len(files3D),prefix='Progress:')
    sizes = {}
    for index, filename in enumerate(files3D):
        sceneDir = filename.rsplit('/',1)[0]
        cen_df = cen_dfs[join(sceneDir,'centroids.csv')]
        centroids = {c['object']:[c['X'],c['Y'],c['Z']] for _,c in cen_df.iterrows()}
        theFile = open(filename,'r')
        contents = theFile.read()
        contents = contents.replace(')[',')\n[').replace(') [',')\n[')
        lines = contents.splitlines()
        distances = {} # of each object's 3d points from centroid
        for line in lines:
            if line=='':
                continue
            try:
                elem = list(json.loads(line.replace("'","\"").replace('(','[').replace(')',']').replace('None','null')))
            except Exception as e:
                print(line)
                raise e
            if len(elem)!=3:
                name = repr(elem).rstrip('\n')
            else:
                try:
                    x1,y1,z1 = [centroids[name][0],centroids[name][1],centroids[name][2]]
                except Exception as e:
                    print(cenFile)
                    print(name)
                    raise e
                x2,y2,z2 = [elem[0],elem[1],elem[2]]
                if name not in distances:
                    distances[name] = [sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)]
                    continue
                distances[name].append(sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2))

        for obj,dist in distances.items():
            newName = ast.literal_eval(obj)[0].replace(' ','_')
            if newName not in sizes:
                sizes[newName] = dist
                continue
            sizes[newName].extend(dist)
        theFile.close()
        progress_bar.update(index,len(files3D),\
                            prefix='Progress:',suffix=str(index)+'/'+str(len(files3D)))

    progress_bar.update(len(files3D),len(files3D),\
                         prefix='Progress:',suffix=str(len(files3D))+'/'+str(len(files3D)))

    # For testing:
    #import matplotlib.pyplot as plt
    # vals = pd.Series(sizes['plant']).sort_values().reset_index(drop=True)
    # vals = vals[:len(vals)-int(len(vals)/5)]
    # len(vals)
    # vals.mean()
    # vals.median()
    # vals.mode()[round(len(vals.mode())/2)]
    # vals.plot(kind='bar')
    # plt.show()

    #mean_sizes = {}
    median_sizes = {}
    #mode_sizes = {}
    for obj,dist in sizes.items():
        numObjects = len(dist)
        vals = pd.Series(dist).sort_values().reset_index(drop=True)
        vals = vals[:len(vals)-int(len(vals)/5)] # trim 20% off the larger end to exclude outliers
        #multiply by 2 below to change radius to diameter
        #mean_sizes[obj] = str(vals.mean()*2)+','+str(numObjects)
        median_sizes[obj] = str(vals.median())+','+str(numObjects) # removed the x2 to make values more reasonable
        #mode = vals.mode()
        #mode = mode if isinstance(mode,int) else mode[int(len(mode)/2)]
        #mode_sizes[obj] = str(mode*2)+','+str(numObjects)

    maxCount = max([int(x.split(',')[-1]) for x in median_sizes.values()])
    maxDiameter = max([float(x.split(',')[0]) for x in median_sizes.values()])
    #meanDiameter = np.mean([float(x.split(',')[0]) for x in mean_sizes.values()])
    medianDiameter = np.median([float(x.split(',')[0]) for x in median_sizes.values()])

    outFile = open("data/object_sizes.csv",'w')
    outFile.write("object,diameter,count,confidence\n")
    for obj,dist in median_sizes.items():
        diameter = float(dist.split(',')[0]) if float(dist.split(',')[0])>0 else medianDiameter
        confidence = (int(dist.split(',')[-1])/maxCount) * (maxDiameter/diameter)
        outFile.write(obj+','+str(dist)+','+str(confidence)+'\n')
    outFile.close()
    sys.stdout.write("Processed in %s sec.\n"%str(endTimer(timer)));
    sys.stdout.flush()


def calculateCoords(objects,method='sampling'):
    '''Calculate the coordinates of a list of objects
    based on angles and distances between triplets
    objects: a list of the object names
    method: method of selecting triplets ('sampling' or 'averaging')
    dictionary: a dictionary of all object triplet data
    output: a dictionary of final object locations'''

    if method == 'averaging':
        # load dictionary of all triplets
        pickleData = pickle.load(open("data/triplets_avg.pickle",'rb'))
        dictionary = {}
        for i, objA in enumerate(pickleData['objectA']):
            objB = pickleData['objectB'][i]
            objC = pickleData['objectC'][i]
            comboData = [pickleData['distanceAB'][i],pickleData['distanceAC'][i],
                pickleData['distanceAO'][i],pickleData['angleBAC'][i],
                pickleData['angleOAB'][i],pickleData['angleOAC'][i],pickleData['count'][i]]
            dictionary[f'{objA},{objB},{objC}'] = comboData
        print ("INFO: Loaded triplet data.")

    elif method == 'sampling':
        df = pd.read_csv('./data/triplets.csv')
        df = df.sample(frac=1).reset_index(drop=True)
        df = df.drop_duplicates(subset=['objectA','objectB','objectC'],keep='first')
        dictionary = {}
        for i, row in df.iterrows():
            objA = row['objectA']
            objB = row['objectB']
            objC = row['objectC']
            comboData = [row['distanceAB'],row['distanceAC'],row['distanceAO'],
                         row['angleBAC'],row['angleOAB'],row['angleOAC'],1]
            dictionary[f'{objA},{objB},{objC}'] = comboData

    else:
        print(f'ERROR: Wrong method selected for calculateCoords: {method}.')
        return {}

    # generate every permutation of the given objects and try to find a set
    # of triplets that will contain enough data to calculate all object locations
    objMix = list(permutations(objects,len(objects)))
    random.shuffle(objMix)
    enoughData = True
    for i,objs in enumerate(objMix):
        print ("INFO: Attempt "+str(i+1)+"...")
        enoughData = True # set to false if any object isn't in final list
        # create list of necessary triplets based on input objects
        combos = [[objs[0],objs[1],x] for x in objs[2:]]
        good = []
        for combo in combos: # for each combo
            comboStr = ','.join(combo)
            if comboStr not in dictionary:
                print ("WARNING: Triplet not found in dictionary: " + comboStr)
                continue
            good.append(combo)

        for obj in objects: # if any of the objects aren't in the final list
            if obj not in [x for sublist in good for x in sublist]:
                print ("ERROR: Not enough data for "+obj+". Retrying...")
                enoughData = False
                break
        if enoughData:
            break

    if not enoughData: print ("ERROR: All tries failed. Exiting..."); sys.exit(1)

    combos = good
    print ("INFO: Found good combo.")

    sizes = loadObjectSizes()

    # ensure distance AB is the same for all triplets, so make it equal to max distance AB of all triplets
    all_ab_dists = []
    for combo in combos:
        all_ab_dists.append(float(dictionary[','.join(combo)][0]))
    d_ab = max(all_ab_dists) # universal distance AB for all triplets

    triplets = []
    for combo in combos: # for each combo
        comboStr = ','.join(combo)
        data = dictionary[comboStr] # find triplet data
        print ("INFO: Setting up combo: "+ repr(combo))
        # set up variables
        objA,objB,objC = combo
        #d_ab = float(data[0])   # distance between objA and objB
        d_ac = float(data[1])   # distance between objA and objC
        d_ao = float(data[2])   # distance between objA and camera
        aBAC = math.radians(float(data[3])) # angle BAC
        aOAB = math.radians(float(data[4])) # angle OAB
        aOAC = math.radians(float(data[5])) # angle OAC

        # find necessary values using trig
        a = d_ac*math.cos(aBAC)
        b = d_ac*math.sin(aBAC)
        x = d_ao*math.cos(aOAB)
        y = (d_ac*d_ao*math.cos(aOAC) - a*x) / b
        z = math.sqrt(d_ao**2 - x**2 - y**2)

        # establish centroid locations for A, B, C, and camera
        A = [0,0,0]
        B = [d_ab,0,0]
        C = [a,b,0]
        O = [x,y,z]
        # establish scale of objects so they are proportional to camera's
        # range of sight
        d_bc = math.sqrt(sum((B-C)**2 for B,C in zip(B,C)))
        d_bo = math.sqrt(sum((B-O)**2 for B,O in zip(B,O)))
        d_co = math.sqrt(sum((C-O)**2 for C,O in zip(C,O)))
        s = min([d_ab,d_ac,d_bc,d_ao,d_bo,d_co]) # use smallest distance as scale factor
        triplets.append([objA,objB,objC,A,B,C,O,s]) # objA,objB,objC,camera,scale

    # The following process answers the question:
    # Where would objC2 be located if it were in the coordinate space of objC1, given
    # objA and objB remain in place and camera2 translates to the location of camera1?
    #
    # We will use objA, objB, and camera coordinates to trivially generate a 4th point
    # (midpoint of these 3 points) that will almost certainly be on a different plane
    # than the other 3 points. We use these points to find an affine transform between
    # baseCoords and every other triplet. objA and objB should be virtually identical
    # in every triplet. But camera and 4th point will differ which should be enough
    # to solve for a transformation matrix that can be used to determine where objCX ends
    # up in the base coordinate space.
    pts = [triplets[0][3],triplets[0][4],triplets[0][6]]
    z = list(zip(pts[0],pts[1],pts[2])) # [[x0,x1,x2],[y0,y1,y2],[z0,z1,z2]]
    d = [sum(z[0])/3,sum(z[1])/3,sum(z[2])/3] # trivially generated 4th point
    pts.append(d)
    baseCoords = np.array(pts,np.float32)   # use first triplet as base
    finalCoords = {} # initialize {obj: (x,y,z)} structure
    finalCoords[triplets[0][0]] = triplets[0][3] # add objA coords
    finalCoords[triplets[0][1]] = triplets[0][4] # add objB coords
    finalCoords[triplets[0][2]] = triplets[0][5] # add base objC coords
    finalCoords['CAMERA'] = triplets[0][6] # add camera coords
    finalCoords['SCALE'] = triplets[0][7] # add scale

    for triplet in triplets[1:]:
        pts = [triplet[3],triplet[4],triplet[6]]
        z = list(zip(pts[0],pts[1],pts[2]))
        d = [sum(z[0])/3,sum(z[1])/3,sum(z[2])/3]
        pts.append(d)
        coords = np.array(pts,np.float32)

        # pad with ones to make translations possible
        pad = lambda x: np.hstack([x, np.ones((x.shape[0], 1))])
        unpad = lambda x: x[:,:-1]
        base = pad(baseCoords)
        curr = pad(coords)
        # solve the least squares problem X * A = Y
        # to find the transformation matrix A
        A, res, rank, s = np.linalg.lstsq(curr, base,rcond=-1)
        transform = lambda x: unpad(np.dot(pad(x), A))

        pts.append(triplet[5])            # now add objC back to the set of points
        coords = np.array(pts,np.float32) # and re-apply the transformation so the
        coordsNew = transform(coords)     # current triplet lines up with the base triplet

        # determine the outlier - these are the coordinates for objC
        isNear = lambda p1,p2: sum((x1 - x2)**2 for x1, x2 in zip(p1, p2)) < 0.0001
        corresp = [] # stores all coords from coordsNew which mapped to a baseCoord
        for coord in coordsNew.tolist():
            for baseCoord in baseCoords.tolist():
                if isNear(coord,baseCoord):
                    corresp.append(coord)
                    break
        finalCoords[triplet[2]] = [x for x in coordsNew.tolist() if x not in corresp][0]
        finalCoords['SCALE'] = min(triplet[7],finalCoords['SCALE']) # update scale

    return finalCoords
