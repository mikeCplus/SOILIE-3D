''' Visuo 3D
    v.18.03.14
    Written by Mike Cichonski
    With contributions from Tae Burque
    for the Science of Imagination Laboratory
    Carleton University

    File: collect_data.py
	This file traverses the SUN3D database and calculates
	angles and distances between object triplets in each frame.
	Requires SUN3D JSON label files in the json folder.'''

import json, random, sys, urllib.request, re, gc

from io import BytesIO
import numpy as np
np.set_printoptions(threshold=sys.maxsize)
from mpl_toolkits.mplot3d import Axes3D
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.path as path
from PIL import Image, ImageDraw
from os import makedirs, listdir
from os.path import join, isfile, isdir, dirname, abspath, splitext, exists
from itertools import permutations

from modules import menu
from modules import import_tools as imp
from modules.timer import *

## declare objects ---------------------------------------------- ##
 
class Frame:
    '''represents a single frame'''

    def __init__(self, ID, width, height):
        '''creates a new frame'''
        self.ID = ID           # the frame number
        self.row = []	       # a list of y values
        self.col = []          # a list of x values
        self.data = []         # a list of data corresponding to x and y location
        self.width = width     # width of frame (y)
        self.height = height   # height of frame (x)
        self.loc = None        # location of recording
        self.objects = []      # objects in frame
        self.labels = {}       # {objectName : (x,y) centroid} pairs (2D)
        self.centroids = {}    # {objectName : (x,y,z) centroids in meters} (3D)
        self.objects3d = {}    # {objectName : [(x,y,z)...(x,y,z)] } all 3d points
        self.combos = []       # list of[labelA,labelB,labelC,angZAB,angZAC,angBAC,distAB]
        self.intrinsics = []   # camera intrinsics
        self.extrinsics = []   # camera extrinsics
        self.image = None      # image to export
        self.background = None # original image
        self.depthMap = None   # depth map
        self.xyz = []          # xyz world coords for entire frame
        self.valid = []        # valid world coords corresponding to each [x,y] location

    def addData(self,data,x,y):
        '''add data at specified x,y location'''
        self.row.append(y)
        self.col.append(x)
        self.data.append(data)

    def addObject(self,obj):
        self.objects.append(obj)

    def update(self):
        '''update matrix and image'''
        dataNames = [x.ID for x in self.data]
        self.image = Image.new('RGBA',(self.width,self.height))
        pix = self.image.load()
        for i,pixel in enumerate(zip(self.col, self.row)):
            pix[pixel[0]-1,pixel[1]-1] = self.data[i].colour
        # camera coords
        sys.stdout.write("\tretrieving camera coords:"); sys.stdout.flush()
        t1 = startTimer() #time to retrieve camera coords
        cameraCoords = imp.depth2XYZcamera(self.intrinsics,self.depthMap)
        sys.stdout.write("\t%s sec.\n"%str(endTimer(t1))); sys.stdout.flush()
        # world coords
        sys.stdout.write("\tconverting to world coords:"); sys.stdout.flush()
        t2 = startTimer() #time to change from camera to world coords
        (xyzWorld,self.valid) = imp.camera2XYZworld(cameraCoords,self.extrinsics)
        self.xyz = np.transpose(xyzWorld)
        sys.stdout.write("\t%s sec.\n"%str(endTimer(t2))); sys.stdout.flush()
        return self # to enable cascading

    def calculateCentroids(self,polygons):
        '''calculate centroids of polygons and add to centroids dictionary
        polygons:   a dictionary of object_name:[(x,y)..(x,y)] pairs'''
        sys.stdout.write("\tcalculating centroids:"); sys.stdout.flush()
        t4 = startTimer() #time to calculate the 2D and 3D centroids
        # Get 2D centroids (to place labels in correct place in image)
        for name,coords in polygons.items():
            centX = sum([x for (x,y) in coords])/len(coords)
            centY = sum([y for (x,y) in coords])/len(coords)
            self.labels[name] = (centX,centY)
        # Get 3D centroids
        rangeX = range(self.height)
        rangeY = range(self.width)
        template = [(y,x) for y in rangeY for x in rangeX]
        for name, allCoords in polygons.items():
            coords = [c for c in allCoords if c[0]<self.width \
		      and c[1]<self.height and c[0]>=0 and c[1]>=0]
            if not coords: continue
            vertices = path.Path(coords,closed=True)
            objectPts = vertices.contains_points(template)
            objectPts = np.reshape(objectPts,(self.width,self.height))
            count = 0
            pts3d = []
            for y,col in enumerate(objectPts):
                for x,row in enumerate(col):
                    if row and self.valid[x][y]:
                        xyzCoords = self.xyz[count]
                        pts3d.append(xyzCoords)
                    if self.valid[x][y]:
                        count+=1
            X = [item[0] for item in pts3d]
            Y = [item[1] for item in pts3d]
            Z = [item[2] for item in pts3d]
            if len(X) == 0:
                continue
            X = sum(X)/len(X)
            Y = sum(Y)/len(Y)
            Z = sum(Z)/len(Z)
            self.objects3d[name] = pts3d
            self.centroids[name] = (X,Y,Z)

        sys.stdout.write("\t\t%s sec.\n"%str(endTimer(t4))); sys.stdout.flush()
        return self

    def getAngleDistCombos(self):
        '''get a set of angles and distances between objects'''
        sys.stdout.write("\tcalculating triplets:"); sys.stdout.flush()
        t5 = startTimer()
        names = []		
        for name, _ in self.centroids.items():
            names.append(name)
        combos = []
        for combo in permutations(names,3):
            combos.append('---'.join(combo).split('---'))
        for combo in combos:
            A = np.array(self.centroids[combo[0]])
            B = np.array(self.centroids[combo[1]])
            C = np.array(self.centroids[combo[2]])
            O = np.array([0,0,0])
            BA = B - A
            CA = C - A
            OA = O - A
            # distance AB, AC, AO
            distAB = np.linalg.norm(A-B)
            distAC = np.linalg.norm(A-C)
            distAO = np.linalg.norm(A-O)
            # angle BAC
            cosBAC   = np.dot(BA, CA) / (np.linalg.norm(BA) * np.linalg.norm(CA))
            angleBAC = np.degrees(np.arccos(cosBAC))
            # angle OAB
            cosOAB   = np.dot(OA, BA) / (np.linalg.norm(OA) * np.linalg.norm(BA))
            angleOAB = np.degrees(np.arccos(cosOAB))
            # angle OAC
            cosOAC   = np.dot(OA, CA) / (np.linalg.norm(OA) * np.linalg.norm(CA))
            angleOAC = np.degrees(np.arccos(cosOAC))
            # add to self.combos and format label names
            nameA = combo[0].lstrip("[").rstrip("]").replace("'","").split(",")
            nameA = "_".join([nameA[0].replace(" ","_"),nameA[1].replace(" ","")])
            nameB = combo[1].lstrip("[").rstrip("]").replace("'","").split(",")
            nameB = "_".join([nameB[0].replace(" ","_"),nameB[1].replace(" ","")])
            nameC = combo[2].lstrip("[").rstrip("]").replace("'","").split(",")
            nameC = "_".join([nameC[0].replace(" ","_"),nameC[1].replace(" ","")])
            self.combos.append([nameA,nameB,nameC,str(distAB),str(distAC),str(distAO),\
                                str(angleBAC),str(angleOAB),str(angleOAC)])
        sys.stdout.write("\t\t%s sec.\n"%str(endTimer(t5))); sys.stdout.flush()
        return self

    def drawPolygons(self, polygons):
        '''draw a set of polygons filled with colour of corresponding objects
        polygons:   a dictionary of object_name:[(x,y)..(x,y)] pairs'''
        sys.stdout.write("\tdrawing polygons:"); sys.stdout.flush()
        t6 = startTimer() #time to draw polygons
        if self.image == None:
            print("ERROR: Can't draw to empty image! (update first)")
        else:
            draw = ImageDraw.Draw(self.image)
            for name,coord in polygons.items():
                colour = (255,255,255,140)
                for o in self.objects:
                    if str(o.getName()) == name:
                        colour = o.colour
                draw.polygon(coord,fill=colour)
            for name,coord in self.labels.items():
                if name not in self.centroids:
                    errLog = open (join('data',self.loc,'error.log'),'a')
                    errLog.write(str(self.ID)+". "+name+"\tat "+self.loc+'\n')
                    errLog.close()
                    draw.text(coord,name+'\n(no xyz data)',fill="black")
                    continue
                x= "%.1f" %self.centroids[name][0]
                y= "%.1f" %self.centroids[name][1]
                z= "%.1f" %self.centroids[name][2]
                draw.text(coord,name+'\n('+x+','+y+','+z+')',fill="black")
            del draw
        sys.stdout.write("\t\t%s sec.\n"%str(endTimer(t6))); sys.stdout.flush()
        return self

    def process3dPoints(self,polygons,filePath,plot):
        '''write 3d points for each object to a file, and if option is enabled,
           plot the 3d points in an image with different colour for each object
        polygons:   a dictionary of object_name:[(x,y)..(x,y)] pairs
        filePath:   the path to save the plots
        plot:       number of views for each frame'''
        sys.stdout.write("\tprocessing 3d data:"); sys.stdout.flush()
        t7 = startTimer() #time to process 3d data
        saveLoc = join(filePath,str(self.ID))
        plotFile = open(saveLoc+'.3d','w')
        patches = []
        #-----------------------------------------------#
        if plot:
            if not exists(saveLoc+'/'):
                makedirs(saveLoc+'/')
            fig = plt.figure()
            ax = fig.add_subplot(111,projection='3d')
            ax.scatter([0],[0],[0],c='r',marker='o')
            fig.clf()
        #-----------------------------------------------#
        for name, coords in self.objects3d.items():
            plotFile.write(str(name))
            for coord in coords:
                coord = "\n"+str(tuple(coord))
                plotFile.write(coord)
            #---------------------------------------------------------------#
            if not plot: continue
            # get colour
            colour = [1,1,1]
            for o in self.objects:
                if str(o.getName()) == name:
                    colour = [float(c)/255 for c in o.colour[:-1]]
                    patches.append(mpatches.Patch(color=colour,label=name))
            xyz = zip(*coords)
            if xyz:
                ax.scatter(xyz[0],xyz[1],xyz[2],c=colour,marker='.',alpha=0.003)
            if name in self.centroids:
                xyzCen = self.centroids[name] # add centroid
                ax.scatter([xyzCen[0]],[xyzCen[1]],[xyzCen[2]],c=[0,0,0],marker='x')
            #---------------------------------------------------------------#
        plotFile.close()
        sys.stdout.write("\t\t%s sec.\n"%str(endTimer(t7))); sys.stdout.flush()
        #-------------------------------------------------------------------#
        if plot:
            sys.stdout.write("\tplotting 3d points:"); sys.stdout.flush()
            t8 = startTimer()
            ax.set_xlabel('X-axis')
            ax.set_ylabel('Y-axis')
            ax.set_zlabel('Z-axis')
            ax.legend(handles=patches,loc=3,\
                  bbox_to_anchor=[float(-0.17),float(-0.15)],fontsize=7.5)
            curFig = plt.gcf()
            ax.azim=0
            for count in range(0,plot):
                ax.azim+=(count*(360/plot))
                curFig.savefig(saveLoc+'/'+str(self.ID)+\
                               '-'+'0'*(1/len(str(count)))+\
                               str(count)+'.png', dpi=100)
            sys.stdout.write("\t\t%s sec.\n"%str(endTimer(t8))); sys.stdout.flush()
        plt.close()
        #------------------------------------------------------------------#
        return self
        
    def export(self,filePath,name):
        '''export matrix and image files
        filePath:   the path to the file
        name:       the filename'''
        sys.stdout.write("\texporting files:")
        t9 = startTimer() #time to draw polygons
	# export centroid file
        centroidFile = open (join(filePath,name+'.cen'),'w')
        for objName,coords in self.centroids.items():
            item = objName+' ['+str(coords[0])+','+str(coords[1])+ \
                        ','+str(coords[2])+']\n'
            centroidFile.write(item)
        centroidFile.close()
	# export csv file
        csvFile = open(join(filePath,name+'.csv'),'w')
        csvFile.write('objectA, objectB, objectC, distanceAB, distanceAC,distanceAO, angleOAB, angleOAC, angleBAC\n')
	
        for combo in self.combos:
	        csvFile.write(','.join(combo)+'\n')
        csvFile.close()
            
    # export image file
        image = self.image
        if self.background:
            image = Image.alpha_composite(self.background,image).convert('RGB')
            image.save(join(filePath,name+'.jpg'))
            image.close()
        sys.stdout.write("\t\t%s sec.\n"%str(endTimer(t9))); sys.stdout.flush()
        return self

class Object1:
    '''represents an object in the scene'''

    def __init__(self, ID, name):
        self.ID = ID
        self.name = name
        self.colour = self.setRandomColour()
        self.frames = {}
        self.oldIDs = []
    def updateID(self, ID):
        if ID != self.ID:
            self.oldIDs.append(self.ID)
        self.ID = ID

    def setRandomColour(self):
        R = int(random.random() * 255)
        G = int(random.random() * 255)
        B = int(random.random() * 255)
        
        if R < 100 and G < 100 and B < 100:
            col = random.randrange(0,3)
            if col == 0:
                R+=100
            elif col == 1:
                G+=100
            else:
                B+=100
        return (R,G,B,140) # return in RGBA format (transparency hard-coded at 140)

    # get object name in format: [object,identifier]
    def getName(self):
        splitName = self.name.split(':')
        n = 0
        while n < len(splitName):
            splitName[n] = str(splitName[n].strip())
            n+=1
        if len(splitName) == 1:
            splitName.append(None)
        return splitName
	
    # add Frame to frames dictionary
    def addFrame(self,location,f):
        if location not in self.frames:
            self.frames[location] = []
        if f not in self.frames[location]:
            self.frames[location].append(f)
            

## -------------------------------------------------------------- ##

if __name__ == "__main__":
    
    allObjects  = [] # list to store all objects from all files
    
    # load json files
    jsonFiles = [f for f in listdir('json') \
                 if isfile(join('json',f))]
 
    def processJSON (data,currentPath, local, plot):
        '''process each json file
        data:   the data contained in the json file
        currentPath:    the root path of the database
        local:  True if database is located locally, False if on web
        plot:   number of different views plotted per frame'''
 
        # start json timer
        jsonTimer = startTimer()

        # parse json data into variables
        name = data['name']
        date = data['date']
        frames = data['frames']
        objects = data['objects']
        
        # store indices of the empty frames & objects
        emptyFrames = []
        emptyObjects = []

        for i, f in enumerate(frames):
            if not f or not f['polygon']:
                emptyFrames.append(i)

        for i,o in enumerate(objects):
            if not o:
                emptyObjects.append(i)

        # get camera intrinsics
        K = np.transpose(np.reshape(imp.readValuesFromTxt(join(currentPath,'data',name,'intrinsics.txt'),local),(3,3)))
        
        # get camera extrinsics
        if local:
            exFile = listdir(join('data',name,'extrinsics'))[-1]
        else:
            exFile = re.compile(r'[0-9]*\.txt').findall(urllib.request.urlopen(join(currentPath,'data',name,'extrinsics')).read().decode('utf-8'))[-1]
            extrinsicsC2W = np.transpose(np.reshape(imp.readValuesFromTxt(join(currentPath,'data',name,'extrinsics',exFile),local),(-1,3,4)),(1,2,0))       

	    # print file stats
        print("-- processing data.....", name)
        print("  -- DATE:", date)
        print("  -- # FRAMES:", len(frames))
        print("    -- actual:", len(frames)-len(emptyFrames))
        print("    -- undefined:", len(emptyFrames))
        print("  -- # OBJECTS:", len(objects))
        print("    -- actual:", len(objects)-len(emptyObjects))
        print("    -- undefined:", len(emptyObjects))

        for i, f in enumerate(frames):
            if i in emptyFrames:
                continue
            frameTimer = startTimer()
            sys.stdout.write("\nCalculating Frame "+str(i))
            sys.stdout.write(" coordinates...\n")
            sys.stdout.write("\tgathering frame data:"); sys.stdout.flush()
            # get background image and depth data ----------------#
            imagePath = join(currentPath,"data",name,"image")
            depthPath = join(currentPath,"data",name,"depth")
            if local:
                imageList = listdir(imagePath)
                depthList = listdir(depthPath)
            else:
                # ---------------------------------------------#
                imageList = re.compile(r'[0-9]*\-[0-9]*\.jpg').findall(urllib.request.urlopen(imagePath).read().decode('utf-8'))
                newList = []
                for x in imageList: # remove duplicates
                    if x not in newList:
                        newList.append(x)
                imageList = newList
                # ---------------------------------------------#
                depthList = re.compile(r'[0-9]*\-[0-9]*\.png').findall(urllib.request.urlopen(depthPath).read().decode('utf-8'))
                newList = []
                for x in depthList: # remove duplicates
                    if x not in newList:
                        newList.append(x)
                depthList = newList
                # ---------------------------------------------#

                for img in imageList:
                    fileNum = "0"*(7-len(str(1+i*5)))+str(1+i*5)+"-"
                    if fileNum in img:
                        image = join(imagePath,img)
                        break
                for img in depthList:
                    fileNum = "0"*(7-len(str(1+i*5)))+str(1+i*5)+"-"
                    if fileNum in img:
                        depth = join(depthPath,img)
                        break

                if local:
                    background = Image.open(image,'r').convert('RGBA') 
                else:
                    background = Image.open(BytesIO(urllib.request.urlopen(image).read())).convert('RGBA')

                (width,height) = background.size

                # ---------------------------------------------------- #
                # create frame and fill with data
                currentFrame = Frame(i,width,height)
                currentFrame.loc = name
                currentFrame.background = background
                currentFrame.depthMap = imp.depthRead(depth,local)
                currentFrame.intrinsics = K
                currentFrame.extrinsics = imp.getExtrinsics(extrinsicsC2W,i)
                exceptions   = []
                conflicts    = []
                polygons     = {}
                for polygon in f['polygon']:
                    ID = polygon['object']
                    exists = False
                    for o in allObjects:
                        if objects[ID]['name'] == o.name:
                            currentObject = o
                            currentObject.updateID(ID)
                            exists = True
                            break
                    if not exists: # new object
                        currentObject = Object1(ID,objects[ID]['name'])
                        allObjects.append(currentObject)
                    polygons[str(currentObject.getName())] = []
                    currentObject.addFrame(name,currentFrame)
                    for j, x in enumerate(polygon['x']):
                        x = int(round(x))
                        y = int(round(polygon['y'][j]))
                        polygons[str(currentObject.getName())].append((x,y))
                        if 0 < x <= width and 0 < y <= height:
                            if (y,x) in zip(currentFrame.row,currentFrame.col):
                                conflicts.append(str([(x,y),currentObject.getName()]))
                            else:
                                currentFrame.addData(currentObject,x,y)
                        else:
                            exceptions.append(str([(x,y),currentObject.getName()]))
                    currentFrame.addObject(currentObject)

                filePath = join('data',name)
                try:
                    makedirs(filePath)
                except OSError:
                    if not isdir(filePath):
                        raise
                sys.stdout.write("\t\t%s sec.\n"%str(endTimer(frameTimer)));
                sys.stdout.flush()
                currentFrame = (currentFrame.update()
                               .calculateCentroids(polygons)
                               .getAngleDistCombos() 
                               .drawPolygons(polygons)
                               .process3dPoints(polygons,filePath,plot)
                               .export(filePath,str(i)))

                # uncomment to save exceptions and conflicts to files
                #np.savetxt(join(filePath,str(i)+'.ex'),exceptions,fmt="%s")
                #np.savetxt(join(filePath,str(i)+'.co'),conflicts,fmt="%s")
                sys.stdout.write("\ttotal time for frame %s:"%str(currentFrame.ID))
                currentFrame = None
                sys.stdout.write(" \t%s sec."%str(endTimer(frameTimer))); sys.stdout.flush()
        # END OF processJSON()

    while 1:
        response = menu.mainMenu()
        if response == '1': # process each json file
            response = None
            options = menu.optionMenu()
            if options == "menu": continue # back to main menu
            currentPath = options[0]
            local =       options[1]
            plot  =       options[2]
            startA = startTimer()
            for jNum,jFile in enumerate(jsonFiles):
                startB = startTimer()
                with open(join("json",jFile)) as jData:
                    data = json.load(jData)
                    processJSON(data,currentPath,local,plot) # process each json file
                print("\n** File processed in %s seconds."% str(endTimer(startB)))
                print("** Total: "+str(jNum+1)+ " files processed in %s seconds." % str(endTimer(startA)))
                print("**",len(allObjects),"total objects in %s JSON files.\n" % str(jNum+1))
            # create log file for all the objects in all frames in all locations
            logFile = open(join("data","objects.log"),"w")
            logFile.write("---- All Objects ----\n")
            logFile.write("# - ID - name - RGB - Locations - Old IDs\n")
            for i, o in enumerate(allObjects):
                oldIDs = "N/A"
                if o.oldIDs:
                    oldIDs = " "+str(o.oldIDs)
                line = str(i+1)+" - "+str(o.ID)+" - "+str(o.getName())+" - "+ \
                       str(o.colour[:3])+" - "+str(len(o.frames))+" - "+oldIDs+"\n"
                logFile.write(line)
            logFile.close()
        elif response == '2':
            print("UNAVAILABLE: Working on it...")
        else:
            sys.exit(0)
