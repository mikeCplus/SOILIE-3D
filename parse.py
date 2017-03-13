# -*- coding: utf-8 -*-
''' GET OBJECTS 3D
    v.17.03.12
    A package for Visuo3D
    Written by Mike Cichonski
    for the Science of Imagination Laboratory
    Carleton University

    File: parse.py
	This file processes all the csv files output by run.py and
	averages the values of the object triplets.
	It also estimates relative object sizes using the object's
	largest measured diameter (unable to find true volume due 
	to incomplete 3d data). Requires output from run.py.'''

import fnmatch
import os
import sys
import ast
import pickle
from math import sqrt

from modules.timer import *

if __name__=="__main__":

    # average or fuzzify triplet values =======================###
    sys.stdout.write("Averaging triplets..."); sys.stdout.flush()
    timer = startTimer()
    files = []
    for root, dirnames, filenames in os.walk('output'):
        for filename in fnmatch.filter(filenames, '*.csv'):
            files.append(os.path.join(root, filename))

    averages = {}
    for filename in files:
        if filename=='output/object_sizes.csv' or filename=='output/triplets.csv':
            continue
        csv = open(filename,'r')
        lines = csv.readlines()

        for line in lines[1:]:
            values = line.split(',')
            objA = values[0].rsplit('_',1)[0]
            objB = values[1].rsplit('_',1)[0]
            objC = values[2].rsplit('_',1)[0]
            triplet = ','.join([objA,objB,objC])
            angOAB = float(values[3])
            angOAC = float(values[4])
            angBAC = float(values[5])
            distAB = float(values[6])
            if triplet not in averages:
                averages[triplet] = [[angOAB],[angOAC],[angBAC],[distAB],1]
                continue
            averages[triplet][0].append(angOAB)
            averages[triplet][1].append(angOAC)
            averages[triplet][2].append(angBAC)
            averages[triplet][3].append(distAB)
            averages[triplet][4]+=1

    triplets = {}
    tripletsFile = open('output/triplets.csv','w')
    tripletsFile.write("objectA,objectB,objectC,angleOAB,angleOAC,angleBAC,distanceAB,count\n")
    for triplet, values in averages.iteritems():
        triplets[triplet] = [sum(values[0])/values[4],\
                             sum(values[1])/values[4],\
                             sum(values[2])/values[4],\
                             sum(values[3])/values[4],values[4]]
        text = ','.join([str(t) for t in triplets[triplet]])
        tripletsFile.write(triplet+','+text+'\n')
    tripletsFile.close()

    with open ('output/triplets.pickle','wb') as handle:
        pickle.dump(triplets,handle,protocol=pickle.HIGHEST_PROTOCOL)
    handle.close()
    sys.stdout.write("Done! (%s sec.)\n"%str(endTimer(timer))); sys.stdout.flush()

    # approximate object sizes =============================###

    def printProgressBar (iteration, total, prefix = '', \
                          suffix = '', decimals = 1, \
                          length = 40, fill = '█'):
        percent = ("{0:."+str(decimals)+"f}"\
                  ).format(100*(iteration/float(total)))
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + '-' * (length - filledLength)
        print '\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix),'\r',
        if iteration == total:
            print ''


    sys.stdout.write("Approximating object diameters...\n"); sys.stdout.flush()
    timer = startTimer()
    files3D = []
    cenFiles = []
    count = 0
    for root, dirnames, filenames in os.walk('output'):
        for filename in fnmatch.filter(filenames,'*.3d'):
            files3D.append(os.path.join(root,filename))
        for filename in fnmatch.filter(filenames,'*.cen'):
            cenFiles.append(os.path.join(root,filename)) 

    files3D.sort()
    cenFiles.sort()
    
    printProgressBar(0,len(cenFiles),prefix='Progress:')
    sizes = {}
    for index, cenFile in enumerate(cenFiles):
        theFile = open(cenFile,'r')
        lines = theFile.readlines()
        centroids = {}
        for line in lines:
            splitline = line.split(' [')
            centroids[splitline[0]] = ast.literal_eval('['+splitline[1])
        theFile.close()
        theFile = open(files3D[index],'r')
        lines = theFile.readlines()
        distances = {} # of each object's 3d points from centroid
        name = lines[0].rstrip('\n')
        for line in lines:
            elem = ast.literal_eval(line)
            if len(elem)!=3:
                name = repr(elem).rstrip('\n')
            else:
                x1,y1,z1 = [centroids[name][0],centroids[name][1],\
                            centroids[name][2]]
                x2,y2,z2 = [elem[0],elem[1],elem[2]]
                if name not in distances:
                    distances[name] = [sqrt((x2-x1)**2 + (y2-y1)**2 +\
                                            (z2-z1)**2)]
                    continue
                distances[name].append(sqrt((x2-x1)**2 + (y2-y1)**2 +\
                                            (z2-z1)**2))

        for obj,dist in distances.iteritems():
            distances[obj] = max(dist)
        
        for obj,dist in distances.iteritems():
            newName = ast.literal_eval(obj)[0].replace(' ','_')
            if newName not in sizes:
                sizes[newName] = [dist]
                continue
            sizes[newName].append(dist)    
        theFile.close()
        printProgressBar(index,len(cenFiles),\
                         prefix='Progress:',suffix=str(index)+'/'+str(len(cenFiles)))

    printProgressBar(len(cenFiles),len(cenFiles),\
                         prefix='Progress:',suffix=str(len(cenFiles))+'/'+str(len(cenFiles)))

    for obj,dist in sizes.iteritems():
        numObjects = len(dist)
        #multiply by 2 below to change radius to diameter
        sizes[obj] = str(max(dist)*2)+','+str(numObjects)
    
    outFile = open("output/object_sizes.csv",'w')
    outFile.write("object,diameter,count\n")
    for obj,dist in sizes.iteritems():
        outFile.write(obj+','+str(dist)+'\n')
    outFile.close()
    sys.stdout.write("Processed in %s sec.\n"%str(endTimer(timer)));
    sys.stdout.flush()
