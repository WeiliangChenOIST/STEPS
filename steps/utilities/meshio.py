# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# STEPS - STochastic Engine for Pathway Simulation
# Copyright (C) 2007-2009 Okinawa Institute of Science and Technology, Japan.
# Copyright (C) 2003-2006 University of Antwerp, Belgium.
#
# See the file AUTHORS for details.
#
# This file is part of STEPS.
#
# STEPS is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# STEPS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

""" Mesh loading and saving tools. 

A STEPS Tetmesh object can be created from output from outside mesh-generators.
Current support for CUBIT (http://cubit.sandia.gov/) and tetgen (http://tetgen.berlios.de/)

Once a Tetmesh object has been created the data can be saved to two separate files: 
	- An xml annotated file containing the nodes, triangles and tetrahedra.
	- A text file containing further information needed by STEPS solvers found in
		Tetmesh object constructor. 
This is intened to drastically reduce mesh-loading time for large meshes 
(over ~100,000 voxels). By storing all data required by STEPS internally in these two files 
this infomation does not have to be found each time by the Tetmesh object constructor. 
"""

import numpy
import time
import steps.geom as stetmesh
import os.path as opath

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


""" Support for TetGen, a freely available tetrahedral mesh generator.
Currently, the module only offers support for reading TetGen files 
generated by calling TetGen from the command line. """

#############################################################################################

def readTetgen(pathroot, compmap = None, patchmap = None, patchiomap = None):
    """Read a TetGen-generated or refined mesh from a set of files.
    
    The TetGen file format for describing a mesh actually consists of 
    multiple files with varying suffixes. Currently, this routine only
    reads meshes consisting of three files:
    
        1/ <input>.node: describing the tetrahedral mesh node points.
        2/ <input>.ele: describing tetrahedral elements, each of which
           consists of 4 pointers into the <input>.node file. (TetGen
           also supports 10-node elements; these 6 extra nodes are obviously 
           not read by STEPS.) 
        3/ <input>.face: describing triangular faces, each of which 
           consists of 3 pointers into the <input>.node file. This file
           is optional.
    
    Other files are .vol (list of maximum volumes), .var (variant constraints)
    .neigh (list of neighbours), .smesh (simple PLC descriptions) and .edge
    (list of boundary edges) files. None of these seem relevant for our
    use cases, so we don't load them even when they are there. In particular,
    the .neigh file is computed by STEPS itself.
    
    Please refer to the TetGen manual (pages 31-40 in the last edition)
    for more information on these file formats:
    
        tetgen.berlios.de/files/tetgen-manual.pdf
    
    INDEXING
    
    Within STEPS, indexing of nodes and elements must start from 
    zero, whereas numbering in TetGen can optionally start from 1. This is 
    detected from the .node file and followed consequently in the .ele and
    .face files. If the indices start from 1, they are transformed by
    subtracting 1 from them while reading. 
    
    COMPARTMENT/PATCH ANNOTATION
    
    TetGen files record the volume and surface materials of tetrahedral and 
    triangular elements by marking them with integer numbers. In TetGen 
    terminology, compartments are called 'region attributes' and patches are 
    called 'boundary markers'. If region attributes or boundary markers
    are present in the .ele or .face file respectively, these are returned
    by the function (see section RETURNS).
    
    Annotation (= the task of assigning groups of tetrahedrons and triangles 
    to Comp and Patch objects, respectively) of the mesh can also be done 
    automatically by this function, if the caller provides dictionaries that 
    map integers to Compartment and Patch id's.
    
    More specifically, this method can automatically generate Comp objects
    if parameter 'compmap' is provided (the default value for this parameter
    is None, in which case no tetrahedron annotation takes place). compmap
    must be a dictionary that projects integer values (corresponding to 
    region attributes found in the .face file) to id strings.
    
    To automatically generate patches, a similar dictionary (called 
    'patchmap') must be provided that maps integer values (corresponding to
    boundary markers found in the .face file) to Patch id's. Additionally,
    a dictionary 'patchiomap' is required that, for each Patch id, returns 
    a tuple of id's refering to the inner and outer Comp objects relative to 
    the Patch. Therefore, automatic Patch generation only works if automatic 
    compartment generation is also requested. 
    
    (See the documentation for steps.geom.tetmesh to understand the 
    relationships between TetMesh, Comp and Patch objects.) 
    
    PARAMETERS:
        pathroot
            The root of the path name. E.g. mesh/torus would make this
            routine try to read files mesh/torus.node, mesh/torus.ele 
            and optionally for mesh/torus.face
        compmap
            Optional: a dictionary mapping integer values to Comp id strings.
            If None (=default), Comp objects are not created automatically.
        patchmap
            Optional: a dictionary mapping integers to Patch id strings.
            If None (=default), Patch objects are not created automatically.
        patchiomap
            Optional: a dictionary mapping a Patch id string to a tuple 
            of strings or None objects. The first element is the id of the
            inner Comp object, the second element of the tuple is the id of
            the outer Comp object.
            If None (=default), Patch objects are not created automatically.
    
    RETURNS:
        A tuple (tetmesh, comps, patches). 
        tetmesh 
            The STEPS TetMesh object
        comps 
            A list of integer values corresponding to the region attributes 
            found in the .ele file. If no region attributes were found, it
            returns None.
        patches
            A list of integer values corresponding to the boundary markers 
            found in the .face file. If the .face file does not exist, or
            if no boundary markers were found, it returns None.
    
    RAISES:
        Exception handling still needs to be incorporated for this routine.
    """
    nodefname = pathroot + '.node'
    elefname = pathroot + '.ele'
    facefname = pathroot + '.face'
    # Is there a .node file?
    if not opath.isfile(nodefname):
        print nodefname
        return None
    if not opath.isfile(elefname):
        print elefname
        return None
    if not opath.isfile(facefname):
        facefname = ''
    
    # Try to read the node file.
    nodefile = open(nodefname, 'r')
    # First line is:  <x> <y> <z> [att<# of points> <dimension (3)> <# of attributes>
    #                <boundary marker (0 or 1)>
    line = nodefile.readline()
    tokens = line.split()
    assert len(tokens) == 4
    nnodes = int(tokens[0])
    assert nnodes > 0
    ndims = int(tokens[1])
    assert ndims == 3
    nattribs = int(tokens[2])
    bmarkers = int(tokens[3])
    idxshift = 0
    # Construct appropriate data structure.
    nodes = numpy.empty((nnodes, ndims))
    # Read until we have all nodes.
    for nodeno in xrange(0, nnodes):
        line = nodefile.readline()
        commentstart = line.find('#')
        if commentstart != -1:
            line = line[0:commentstart]
        # Remaing lines: <point #>ributes] 
        #                [boundary marker]
        tokens = line.split()
        if len(tokens) == 0: 
            continue
        nodeidx = int(tokens[0])
        if nodeno == 0:
            idxshift = nodeidx
        idx2 = nodeidx - idxshift
        nodes[idx2,0] = float(tokens[1])
        nodes[idx2,1] = float(tokens[2])
        nodes[idx2,2] = float(tokens[3])
    # Close the file.
    nodefile.close()

    # Try to read the .ele file.
    elefile = open(elefname, 'r')
    # First line: <# of tetrahedra> <nodes per tet. (4 or 10)>
    #             <region attribute (0 or 1)>
    line = elefile.readline()
    tokens = line.split()
    assert len(tokens) == 3
    ntets = int(tokens[0])
    assert ntets > 0
    nodespertet = int(tokens[1])
    assert (nodespertet == 4) or (nodespertet == 10)
    attridx = 1 + nodespertet
    tetregattrib = int(tokens[2])
    assert (tetregattrib == 0) or (tetregattrib == 1)
    # Construct appropriate data structure.
    tets = numpy.empty((ntets, 4), dtype = int)
    comps = [ ]
    # Read until we have all the elements.
    for eleno in xrange(0, ntets):
        line = elefile.readline()
        commentstart = line.find('#')
        if commentstart != -1:
            line = line[0:commentstart]
        # Remaining lines: <tetrahedron #> <node> ... <node> [attribute]
        tokens = line.split()
        if len(tokens) == 0: 
            continue
        tetidx = int(tokens[0]) - idxshift
        tets[tetidx, 0] = int(tokens[1]) - idxshift
        tets[tetidx, 1] = int(tokens[2]) - idxshift
        tets[tetidx, 2] = int(tokens[3]) - idxshift
        tets[tetidx, 3] = int(tokens[4]) - idxshift
        if tetregattrib == 1:
            comps.append(int(tokens[attridx]))
    if tetregattrib == 1:
        assert len(comps) == ntets
    # Close the file.
    elefile.close() 
    
    # If we have a .face file, try to read it.
    nfaces = 0
    faceregattrib = 0
    faces = None
    patches = [ ]
    if len(facefname) > 0:
        facefile = open(facefname, 'r')
        # Read the first line: <# of faces
        line = facefile.readline()
        tokens = line.split()
        assert len(tokens) == 2
        nfaces = int(tokens[0])
        assert nfaces > 0
        faceregattrib = int(tokens[1])
        assert (faceregattrib == 0) or (faceregattrib == 1)
        # Construct appropriate data structure.
        faces = numpy.empty((nfaces, 3), dtype = int)
        patches = [ ]
        # Read until we have all the elements.
        for faceno in xrange(0, nfaces):
            line = facefile.readline()
            commentstart = line.find('#')
            if commentstart != -1:
                line = line[0:commentstart]
            # Remaining lines: <face #> <node> <node> <node> [bmarker]
            tokens = line.split()
            if len(tokens) == 0: 
                continue
            faceidx = int(tokens[0]) - idxshift
            faces[faceidx, 0] = int(tokens[1]) - idxshift
            faces[faceidx, 1] = int(tokens[2]) - idxshift
            faces[faceidx, 2] = int(tokens[3]) - idxshift
            if faceregattrib == 1:
                patches.append(int(tokens[4]))
        if faceregattrib == 1:
            assert len(patches) == nfaces
        # Close the face file.
        facefile.close()

    # Create the mesh.
    nodes = nodes.flatten()																						#########################
    tets = tets.flatten()																						######  flattening ######
    faces = faces.flatten()																						#########################
    tetmesh = stetmesh.Tetmesh(nodes, tets, faces)
    assert tetmesh != None
    
    # Annotation for compartments and patches.
    if (len(comps) > 0) and (compmap != None):
        # We start with compartments.
        uniqcomps = set(comps)
        # Check whether the provided map covers everything.
        for i in uniqcomps:
            assert i in compmap
        for i in uniqcomps:
            alltets = [ x for x in xrange(0, ntets) if comps[x] == i ]
            newcomp = stetmesh.TmComp(compmap[i], tetmesh, alltets)
        
        # Then we go on with patches.
        if (len(patches) > 0) and (patchmap != None) and (patchiomap != None):
            uniqpatches = set(patches)
            # Check whether the provided maps make sense.
            for i in uniqpatches:
                assert i in patchmap
            for i in uniqpatches:
                alltris = [ x for x in xrange(0, nfaces) if patches[x] == i ]
                patch_n = patchmap[i]
                (icomp_n, ocomp_n) = patchiomap[patch_n]
                icomp = tetmesh.getComp(icomp_n)
                assert icomp != None
                ocomp = None
                if ocomp_n != None:
                    ocomp = tetmesh.getComp(ocomp_n)
                    assert ocomp != None
                np = stetmesh.TmPatch(patch_n, tetmesh, alltris, icomp, ocomp)
    
    # Return the mesh.
    if len(comps) == 0:
        comps = None
    if len(patches) == 0:
        patches = None
    return (tetmesh, comps, patches)

#############################################################################################

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

""" Supoprt for CUBIT (http://cubit.sandia.gov/), a powerful geometry and 
mesh-generation toolkit (license required) which supports generation of
tetrahedral meshes that is imported to STEPS. Output from CUBIT should be
saved in ABAQUS format as this is the only format this script currently 
supports. """

#############################################################################################

def readCubit(filename, scale):

	""" Read a CUBIT-generated tetrahedral mesh saved in ABAQUS format and 
	return the created steps.geom.Tetmesh object.
	
	PARAMETERS:
		1) filename: the CUBIT exported filename (or path) including any suffix.
			Must be in abacus format.
		2) scale: LENGTH scale from the cubit mesh to real geometry. e.g. a radius 
		   of 10 in CUBIT to a radius of 1 micron in STEPS, scale is 1e-7.
	
	INDEXING:
	Within STEPS, indexing of nodes, triangles and tetrahedrons must start at 0,
	whereas indexing in CUBIT begins at 1. So the resulting indices in STEPS 
	are equal to the indices in CUBIT minus 1. Therefore information about the 
	mesh elements can be passed between STEPS and CUBIT (e.g. a compartment in 
	STEPS could be highlighted and viewed in CUBIT) but the user should take 
	care to allow for this difference of 1.
	note: The triangle indices will not be related to each other because this 
	information is not exported by CUBIT.
	
	For large meshes (over ~100,000 voxels) creation of STEPS Tetmesh can be time consuming.
	Therefore it is advised to only use this method once, and use meshio.py to save mesh in
	XML and ASCII format for quick loading in future.
	Example use:
		>>> import meshio
		>>> cubitfilename = '/cubit_meshes/spine.inp'
		>>> ### Use this function to create steps.geom.Tetmesh object from CUBIT output file ###
		>>> mymesh = meshio.readCubit(cubitfilename, 1e-6)
		>>> ### Save this mesh in XML (and ASCII) format for quick-loading in future ###
		>>> meshio.saveXML('/meshes/spine1', mymesh)
		>>> ### Mesh saved in /meshes/spine1.xml and /meshes/spine1.txt ###	
	"""
			 
	print "Reading CUBIT file..."
	btime = time.time()
	
	# Try to open the CUBIT file. An error will be thrown if it doesn't exist
	cubfile = open(filename, 'r')
	
	# 1st line is: *HEADING
	# 2nd line is: cubit(<filename>): <date>: <time>
	# 3rd line is: *NODE
	line = cubfile.readline()
	# check we have the right kind of CUBIT output file here
	assert(line == '*HEADING\n')
	line = cubfile.readline() 
	line = cubfile.readline()
	assert(line == '*NODE\n')
	
	# OK, we have the right kind of file here, lets make the data structures
	# Problem is we don't know how big these are going to be at this point
	# For the numpy problem in STEPS 0.5. keep these structures as simple lists
	pnts = []
	tets = []
	# TODO: Look at exporting surface triangles in CUBIT
	
	line = cubfile.readline()
	line= line.replace(',', ' ')
	line = line.split()
	while(line[0] != '*ELEMENT'):
		assert(len(line) == 4)
		nodidx = int(line[0])
		# Create the node to add to the list of nodes
		node = [0.0, 0.0, 0.0]
		# set to the right scale
		node[0] = float(line[1])*scale
		node[1] = float(line[2])*scale
		node[2] = float(line[3])*scale 
		# And add to the list of points. That's all there is to it
		pnts+= node
		# Fetch the next line
		line = cubfile.readline()
		line= line.replace(',', ' ')
		line = line.split()
	assert(pnts.__len__()%3 == 0)
	
	# Now we are on the tets. We can just read to the end of the file now
	line = cubfile.readline()
	while(line):
		line = line.replace(',', ' ')
		line = line.split()
		assert(len(line) == 5)
		tetidx = int(line[0])
		# create the element to add to the list of tets 
		element = [0, 0, 0, 0]
		# Must subtract 1 to get proper indexing (starting at 0, not 1 as in CUBIT output)
		element[0] = int(line[1])-1		
		element[1] = int(line[2])-1
		element[2] = int(line[3])-1
		element[3] = int(line[4])-1
		tets+=element
		line = cubfile.readline()
	assert(tets.__len__()%4 == 0)
	
	print "Read CUBIT file succesfully"
	
	# Output the number of nodes and tets
	print "Number of nodes: ", pnts.__len__()/3
	print "Number of tets: ", tets.__len__()/4
	
	print "creating Tetmesh object in STEPS..."
	mesh = stetmesh.Tetmesh(pnts, tets)
	
	# Check mesh was created properly from this minimal information
	assert(pnts.__len__()/3 == mesh.nverts)
	assert(tets.__len__()/4 == mesh.ntets)
	
	return mesh

#############################################################################################

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

""" Saving and laoding a mesh in XML and ASCII format (in two separate files). 
This allows this data to be shared and dramatically reduces mesh-loading time for larger meshes 
of 10,000s or greater number of voxels. """

#############################################################################################

def saveXML(pathname, tetmesh):
	
	""" Save a STEPS Tetmesh in two separate files: 
	1) an XML file.
	This file stores the basic information about the mesh which tends to be
	common information for any software that supports tetrahedral meshes.
	- NODES are stored by cartesian coordinates.
	- TRIANGLES are stored by the indices of their 3 nodes.
	- TETRAHEDRONS are stored by the indices of their 4 nodes.
	
	 The XML file also stores infomation about any compartments or 
	 patches created in STEPS (class steps.geom.TmComp steps.geom.TmPatch
	 respectively). 
	 - COMPARTMENT(S) are stored by: 
		their string identification.
		a list of any volume systems added to the compartment at time of saving.
		a list of tetrahedrons belonging to the compartment
	 - PATCH(ES) are stored by:
		their string identification.
		a list of any surface systems added to the patch at time of saving.
		the inner compartment id.
		the outer compartment id (if it exists).
		a list of trianlges belonging to this patch.
		
	2) An ASCII file storing information important to STEPS internally. This
	information must be found by STEPS once from the basic mesh infomation and
	is vital for simulations in STEPS. This can take a significant amount of 
	time for larger meshes, so storing this information in this way can drastically
	reduce future mesh loading times. The information stored is:
	- each triangle's area.
	- each triangle's normal.
	- each triangle's two (or one for surface tris) tetrahedron neighbours.
	- each tetrahedron's volume.
	- each tetrahedron's barycenter.
	- each tetrahedron's four neighbouring triangles.
	- each tetrahedron's four (or fewer for surface tets) tetrahedron neighbours.
	
	PARAMETERS:
		1) pathname: the root of the path to store the files. 
			e.g. 'meshes/spine1' will save data in /meshes/spine1.xml and /meshes/spine1.txt
		2) tetmesh: A valid STEPS Tetmesh object (of class steps.geom.Tetmesh). This mesh 
				can be made in a variety of ways, e.g. to save a mesh loaded from tetgen: 
			>>> import meshio
			>>> ### Use cubit script to create steps.geom.Tetmesh object from tetgen output file ###
			>>> mymesh = meshio.readTetgen(tetgenfilename)
			>>> ### Save this mesh in XML (and ASCII) format for quick-loading in future ###
			>>> meshio.saveXML('/meshes/spine1', mymesh[0])
		
	"""
	
	# Performa a basic test on the object itself
	if (tetmesh.__str__()[1:19] != 'steps.geom.Tetmesh'):
		print "2nd parameter not a valid steps.geom.Tetmesh object."
		return 0
	
	# Following will throw IOError if pathname not a valid directory
	xmlfile = open(pathname+'.xml', 'w')
	textfile = open(pathname+'.txt', 'w')
	
	xmlfile.write('<?xml version="1.0" encoding="ISO-8859-1"?>\n')
	xmlfile.write('<tetmesh>\n')
	
	
	### Write the node information  
	
	nverts = tetmesh.countVertices()
	
	xmlfile.write('\t<nodes size = "'+str(nverts)+'">\n')
	textfile.write(str(nverts)+'\n\n')
	
	for node in xrange(nverts):
		# Write indices and coordinates to xml file
		xmlfile.write('\t\t<node idx = "' + str(node) + '">\n')
		coords = str(tetmesh.getVertex(node)).strip(')').strip('(')
		xmlfile.write('\t\t\t<coords>'+ coords + '</coords>\n')
		xmlfile.write('\t\t</node>\n')
	xmlfile.write('\t</nodes>\n')
	
	
	### Write the triangle information
	
	ntris = tetmesh.countTris()
	xmlfile.write('\t<triangles size = "' +str(ntris)+'">\n')
	textfile.write(str(ntris)+'\n')
	
	for tri in xrange(ntris):
		# Write indices and nodes to xml file
		xmlfile.write('\t\t<tri idx = "' + str(tri) + '">\n')
		nodes = str(tetmesh.getTri(tri)).strip(')').strip('(')
		xmlfile.write('\t\t\t<nodes>' + nodes + '</nodes>\n')
		xmlfile.write('\t\t</tri>\n')
		# Write the area, normal, tetneighbours to text file
		textfile.write(str(tetmesh.getTriArea(tri)) + " ")
		norm = tetmesh.getTriNorm(tri)
		textfile.write(str(norm[0]) + " " + str(norm[1]) + " " + str(norm[2]) + " ")
		tetneighb = tetmesh.getTriTetNeighb(tri)
		textfile.write(str(tetneighb[0]) + " " + str(tetneighb[1]) + " ")
		textfile.write('\n')
	xmlfile.write('\t</triangles>\n')
	
	
	### Write the tetrahedron information
	
	ntets = tetmesh.countTets()
	xmlfile.write('\t<tetrahedrons size = "' +str(ntets)+'">\n')
	textfile.write('\n' +str(ntets)+'\n')
	
	for tet in xrange(ntets):
		# Write indices and nodes to xml file
		xmlfile.write ('\t\t<tet idx = "' + str(tet) + '">\n')
		nodes = str(tetmesh.getTet(tet)).strip(')').strip('(')
		xmlfile.write('\t\t\t<nodes>' + nodes + '</nodes>\n')
		xmlfile.write('\t\t</tet>\n')
		# Write the volume, barycenter, trineighbours, tetneighbours to xml file
		textfile.write(str(tetmesh.getTetVol(tet)) + " ")
		baryc = tetmesh.getTetBarycenter(tet)
		textfile.write(str(baryc[0]) + " " + str(baryc[1]) + " " + str(baryc[2]) + " ")
		trineighb = tetmesh.getTetTriNeighb(tet)
		textfile.write(str(trineighb[0])+" "+str(trineighb[1])+" "+str(trineighb[2])+" "+str(trineighb[3])+" ")
		tetneighb = tetmesh.getTetTetNeighb(tet)
		textfile.write(str(tetneighb[0])+" "+str(tetneighb[1])+" "+str(tetneighb[2])+" "+str(tetneighb[3])+" ")
		textfile.write('\n')
	xmlfile.write('\t</tetrahedrons>\n')
	
	
	### Write the comp and patch information. 
	# TODO: Changes need to be made to steps code to make it easier to get the tet
	# and tri members. Currently the mesh returns base pointer (Comp or Patch) 
	# which cannot be used to find the indices. 
	
	comps = tetmesh.getAllComps()
	ncomps = comps.__len__()
	xmlfile.write('\t<compartments size = "' + str(ncomps) + '">\n')
	
	if (ncomps > 0) :
		ids = []
		vsys=[]
		tets = []
		for c in xrange(ncomps):
			ids.append(comps[c].getID())
			vsys.append(comps[c].getVolsys())
			tets.append([])
		assert(tets.__len__() == ncomps)
		# Only choice right now is to loop over all tets and compare comp to tet id
		for tet in xrange(ntets):
			comptemp = tetmesh.getTetComp(tet)
			if not comptemp: continue
			idtemp = comptemp.getID()
			for c in xrange(ncomps):
				if idtemp == ids[c]:
					tets[c].append(tet)
					break
		# Now we have the tet members of each comp, we can write this to xml
		for c in xrange(ncomps):
			xmlfile.write('\t\t<comp idx = "' +str(c) + '">\n')
			xmlfile.write('\t\t\t<id>' + ids[c] + '</id>\n')
			xmlfile.write('\t\t\t<volsys>')
			for v in vsys[c]:
				if (v != vsys[c][0]) : xmlfile.write(',')
				xmlfile.write(v)
			xmlfile.write('</volsys>\n')
			xmlfile.write('\t\t\t<tets>')
			for t in tets[c]:
				if (t != tets[c][0]) : xmlfile.write(',')
				xmlfile.write(str(t))
			xmlfile.write('</tets>\n')
			xmlfile.write('\t\t</comp>\n')
	xmlfile.write('\t</compartments>\n')
	
	patches = tetmesh.getAllPatches()
	npatches = patches.__len__()
	xmlfile.write('\t<patches size = "' + str(npatches) + '">\n')
	
	if (npatches > 0) :
		ids = []
		ssys = []
		icomp=[]
		ocomp=[]
		tris = []
		for p in xrange(npatches):
			ids.append(patches[p].getID())
			ssys.append(patches[p].getSurfsys())
			icomp.append(patches[p].getIComp().getID())
			if (not patches[p].getOComp()): ocomp.append('null')
			else : ocomp.append(patches[p].getOComp().getID())
			tris.append([])
		assert(ids.__len__() == ssys.__len__() == icomp.__len__() == ocomp.__len__() == tris.__len__() == npatches)
		
		for tri in xrange(ntris):
			patchtemp = tetmesh.getTriPatch(tri)
			if not patchtemp: continue
			idtemp = patchtemp.getID()
			for p in xrange(npatches):
				if idtemp == ids[p]:
					tris[p].append(tri)
					break
		# Write all to xml
		for p in xrange(npatches):
			xmlfile.write('\t\t<patch idx = "'+str(p) + '">\n')
			xmlfile.write('\t\t\t<id>' + ids[p] + '</id>\n')
			xmlfile.write('\t\t\t<surfsys>')
			for s in ssys[p]:
				if (s != ssys[p][0]) : xmlfile.write(',')
				xmlfile.write(s)
			xmlfile.write('</surfsys>\n')
			xmlfile.write('\t\t\t<icomp>' + icomp[p] + '</icomp>\n')
			xmlfile.write('\t\t\t<ocomp>' + ocomp[p] + '</ocomp>\n')
			xmlfile.write('\t\t\t<tris>')
			for t in tris[p]:
				if (t != tris[p][0] ) : xmlfile.write(',')
				xmlfile.write(str(t))
			xmlfile.write('</tris>\n')
			xmlfile.write('\t\t</patch>\n')
	xmlfile.write('\t</patches>\n')
	
	
	xmlfile.write('</tetmesh>')
	
	xmlfile.close()
	textfile.close()

#############################################################################################

def loadXML(pathname):
	""" Load a mesh in STEPS from the XML (and ASCII) file. This will
	work with just the XML file, but this is akin to creating the mesh in STEPS
	from scratch and really negates the use of storing the mesh infomation at all.
	For maximum benefit the XML file should be accompanied by the ASCII file, which
	contains all the internal information.
	 
	PARAMETERS:
		1) pathname: the root of the path where the file(s) are stored. 
			e.g. with 'meshes/spine1' this function will look for files /meshes/spine1.xml 
			and /meshes/spine1.txt
	
	RETURNS: A tuple (mesh, comps, patches)
		mesh 
			The STEPS Tetmesh object (steps.geom.Tetmesh)
		comps
			A list of any compartment objects (steps.geom.TmComp) from XML file 
		patches
			A list of any patches objects (steps.geom.TmPatch) from XML file 
	"""


	# Try to open the XML file. An error will be thrown if it doesn't exist
	xmlfile = open(pathname+'.xml', 'r')

	# Try to open the text file. A warning will be shown and a flag set if it doesn't exist	
	havetxt = True
	try :
		textfile = open(pathname+'.txt', 'r')
	except:
		havetxt = False
	if (havetxt == False) : print "WARNING: text file not found. Will construct mesh from information in XML file only."
	
	# Perform a basic check to see if we have the expected kind of file which has not been altered.
	info = xmlfile.readline()
	if(xmlfile.readline().rstrip() != '<tetmesh>'):
		print 'XML file is not a recognised STEPS mesh file'
		return
	
	# Collect basic node information and perform some checks on the data read from XML file
	nodeinfo = xmlfile.readline().strip()
	assert(nodeinfo.__len__() > 17)
	assert(nodeinfo[-2:] == '">')
	nnodes = int(nodeinfo[15:-2])
	if (havetxt): assert (nnodes == int(textfile.readline()))
	
	nodes_out = numpy.zeros(nnodes*3)
	for i in xrange(nnodes):
		idxtemp = xmlfile.readline().strip()
		assert(int(idxtemp[13:-2]) == i)
		coordtemp = xmlfile.readline().strip()
		assert(coordtemp[:8] == '<coords>' and coordtemp[-9:] == '</coords>')
		coordtemp = coordtemp[8:-9].split(', ')
		nodes_out[i*3], nodes_out[(i*3)+1], nodes_out[(i*3)+2] = float(coordtemp[0]), float(coordtemp[1]), float(coordtemp[2])
		assert(xmlfile.readline().strip() == '</node>')
	
	assert(xmlfile.readline().strip() == '</nodes>')
	
	# Now read triangle information from xml file and text file if we have it
	triinfo = xmlfile.readline().strip()
	assert(triinfo.__len__() > 21)
	assert(triinfo[-2:] == '">')
	ntris = int(triinfo[19:-2])
	if (havetxt) : 
		textfile.readline()
		assert (ntris == int(textfile.readline()))

	tris_out = numpy.zeros(ntris*3, dtype = 'int')
	if (havetxt) :
		triareas_out = numpy.zeros(ntris)
		trinorms_out = numpy.zeros(ntris*3)
		tritetns_out = numpy.zeros(ntris*2, dtype = 'int')
	
	for i in xrange(ntris):	
		idxtemp = xmlfile.readline().strip()
		assert(int(idxtemp[12:-2]) == i)
		nodetemp = xmlfile.readline().strip()
		assert (nodetemp[:7] == '<nodes>' and nodetemp[-8:] == '</nodes>')
		nodetemp = nodetemp[7:-8].split(', ')
		tris_out[i*3], tris_out[(i*3)+1], tris_out[(i*3)+2] = int(nodetemp[0]), int(nodetemp[1]), int(nodetemp[2])
		assert(xmlfile.readline().strip() == '</tri>')
		# Now read the text file, if it exists, and get the extra information
		if (havetxt):
			line = textfile.readline().rstrip().split(" ")
			assert(line.__len__() == 6)
			triareas_out[i], trinorms_out[i*3], trinorms_out[(i*3)+1], trinorms_out[(i*3)+2] = float(line[0]), float(line[1]), float(line[2]), float(line[3])
			tritetns_out[i*2], tritetns_out[(i*2)+1] = int(line[4]), int(line[5])		
	assert(xmlfile.readline().strip() == '</triangles>')
	
	# Now read tet information from xml file and text file if we have it
	tetinfo = xmlfile.readline().strip()
	assert(tetinfo.__len__() > 24)
	assert(tetinfo[-2:] == '">')
	ntets = int(tetinfo[22:-2])
	if (havetxt) :
		textfile.readline()
		assert(ntets == int(textfile.readline()))	
	
	tets_out = numpy.zeros(ntets*4, dtype = 'int')
	if (havetxt): 
		tetvols_out = numpy.zeros(ntets)
		tetbarycs_out = numpy.zeros(ntets*3)
		tettrins_out = numpy.zeros(ntets*4, dtype = 'int')
		tettetns_out = numpy.zeros(ntets*4, dtype = 'int')
	for i in xrange(ntets):	
		idxtemp = xmlfile.readline().strip()
		assert(int(idxtemp[12:-2]) == i)
		nodetemp = xmlfile.readline().strip()
		assert (nodetemp[:7] == '<nodes>' and nodetemp[-8:] == '</nodes>')		
		nodetemp = nodetemp[7:-8].split(', ')
		tets_out[i*4], tets_out[(i*4)+1], tets_out[(i*4)+2], tets_out[(i*4)+3] = int(nodetemp[0]), int(nodetemp[1]), int(nodetemp[2]), int(nodetemp[3])
		assert(xmlfile.readline().strip() == '</tet>')
		# Read the text file if we have it and get further information
		if (havetxt):
			line = textfile.readline().rstrip().split(" ")
			assert (line.__len__() == 12)
			tetvols_out[i], tetbarycs_out[i*3], tetbarycs_out[(i*3)+1], tetbarycs_out[(i*3)+2] = float(line[0]), float(line[1]), float(line[2]), float(line[3])
			tettrins_out[i*4], tettrins_out[(i*4)+1], tettrins_out[(i*4)+2], tettrins_out[(i*4)+3] = int(line[4]), int(line[5]), int(line[6]), int(line[7])
			tettetns_out[i*4], tettetns_out[(i*4)+1], tettetns_out[(i*4)+2], tettetns_out[(i*4)+3] = int(line[8]), int(line[9]), int(line[10]), int(line[11])
	assert(xmlfile.readline().strip() == '</tetrahedrons>')

	# We have all the information now. Time to make the Tetmesh object. New constructor keeps the order, which is:
	# nodes, tris, tri areas, tri normals, tri tet neighbours, tets, tet volumes, tet barycenters, tet tri neighbs, tet tet neighbs.
	mesh = stetmesh.Tetmesh(nodes_out, tris_out, triareas_out, trinorms_out, tritetns_out, tets_out, tetvols_out, tetbarycs_out, tettrins_out, tettetns_out)
	
	# Now fetch any comp and patch information from XML file
	compinfo = xmlfile.readline().strip()
	assert(compinfo.__len__() > 24)
	assert(compinfo[-2:] == '">')
	ncomps = int(compinfo[22:-2])
	comps_out = []
	for i in xrange(ncomps):
		idxtemp = xmlfile.readline().strip()
		assert(int(idxtemp[13:-2]) == i)
		idtemp = xmlfile.readline().strip()
		assert(idtemp[:4] == '<id>' and idtemp[-5:] == '</id>')
		idtemp = idtemp[4:-5]
		volsystemp = xmlfile.readline().strip()
		assert(volsystemp[:8] == '<volsys>' and volsystemp[-9:] == '</volsys>')
		volsystemp = volsystemp[8:-9].split(',')
		if (volsystemp[0] == '') : volsystemp = []
		tettemp = xmlfile.readline().strip()
		assert(tettemp[:6] == '<tets>' and tettemp[-7:] == '</tets>')
		tettemp = tettemp[6:-7].split(',')
		nctets = tettemp.__len__()
		ctets = numpy.zeros(nctets, dtype = 'int')
		for ct in xrange(nctets): ctets[ct] = int(tettemp[ct])
		c_out = stetmesh.TmComp(idtemp, mesh, ctets)
		for v in volsystemp: c_out.addVolsys(v)
		comps_out.append(c_out)	
		assert(xmlfile.readline().strip() == '</comp>')
	assert(xmlfile.readline().strip() == '</compartments>')
	
	# Retrieve patch info
	patchinfo = xmlfile.readline().strip()
	assert(patchinfo.__len__() > 19)
	assert(patchinfo[-2:] == '">')
	npatches = int(patchinfo[17:-2])
	patches_out = []
	for i in xrange(npatches):
		idxtemp = xmlfile.readline().strip()
		assert(int(idxtemp[14:-2]) == i)
		idtemp = xmlfile.readline().strip()
		assert(idtemp[:4] == '<id>' and idtemp[-5:] == '</id>')
		idtemp = idtemp[4:-5]
		surfsystemp = xmlfile.readline().strip()
		assert(surfsystemp[:9] == '<surfsys>' and surfsystemp[-10:] == '</surfsys>')
		surfsystemp = surfsystemp[9:-10].split(',')
		if (surfsystemp[0] == '') : surfsystemp = []
		icomptemp = xmlfile.readline().strip()
		assert(icomptemp[:7] == '<icomp>' and icomptemp[-8:] == '</icomp>')
		icomptemp = icomptemp[7:-8]
		ocomptemp = xmlfile.readline().strip()
		assert(ocomptemp[:7] == '<ocomp>' and ocomptemp[-8:] == '</ocomp>')
		ocomptemp = ocomptemp[7:-8]		
		tritemp = xmlfile.readline().strip()
		assert(tritemp[:6] == '<tris>' and tritemp[-7:] == '</tris>')		
		tritemp = tritemp[6:-7].split(',')
		nptris = tritemp.__len__()
		ptris = numpy.zeros(nptris, dtype='int')
		for pt in xrange(nptris): ptris[pt] = int(tritemp[pt])
		if (ocomptemp != 'null'): p_out = stetmesh.TmPatch(idtemp, mesh, ptris, mesh.getComp(icomptemp), mesh.getComp(ocomptemp))
		else :  p_out = stetmesh.TmPatch(idtemp, mesh, ptris, mesh.getComp(icomptemp))
		for s in surfsystemp: p_out.addSurfsys(s)
		patches_out.append(p_out)
		assert(xmlfile.readline().strip() == '</patch>')
	assert(xmlfile.readline().strip() == '</patches>')

	
	return (mesh,comps_out,patches_out)

#############################################################################################

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #