"""
The printableObject module contains a printableObject class,
which is used to represent a single object that can be printed.
A single object can have 1 or more meshes which represent different sections for multi-material extrusion.
"""
__copyright__ = "Copyright (C) 2013 David Braam - Released under terms of the AGPLv3 License"

import time
import math
import os
from Cura.util.mesh import Mesh

import numpy
numpy.seterr(all='ignore')

from Cura.util import polygon

class printableObject(object):
	"""
	A printable object is an object that can be printed and is on the build platform.
	It contains 1 or more Meshes. Where more meshes are used for multi-extrusion.

	Each object has a 3x3 transformation matrix to rotate/scale the object.
	This object also keeps track of the 2D boundary polygon used for object collision in the objectScene class.
	"""
	def __init__(self, originFilename):
		self._originFilename = originFilename
		if originFilename is None:
			self._name = 'None'
		else:
			self._name = os.path.basename(originFilename)
		if '.' in self._name:
			self._name = os.path.splitext(self._name)[0]
		self._meshList = []
		self._position = numpy.array([0.0, 0.0])
		self._matrix = numpy.matrix([[1,0,0],[0,1,0],[0,0,1]], numpy.float64)
		self._transformedMin = None
		self._transformedMax = None
		self._transformedSize = None
		self._boundaryCircleSize = None
		self._drawOffset = None
		self._boundaryHull = None
		self._printAreaExtend = numpy.array([[-1,-1],[ 1,-1],[ 1, 1],[-1, 1]], numpy.float32)
		self._headAreaExtend = numpy.array([[-1,-1],[ 1,-1],[ 1, 1],[-1, 1]], numpy.float32)
		self._headMinSize = numpy.array([1, 1], numpy.float32)
		self._printAreaHull = None
		self._headAreaHull = None
		self._headAreaMinHull = None

		self._loadAnim = None

	def copy(self):
		ret = printableObject(self._originFilename)
		ret._matrix = self._matrix.copy()
		ret._transformedMin = self._transformedMin.copy()
		ret._transformedMax = self._transformedMax.copy()
		ret._transformedSize = self._transformedSize.copy()
		ret._boundaryCircleSize = self._boundaryCircleSize
		ret._boundaryHull = self._boundaryHull.copy()
		ret._printAreaExtend = self._printAreaExtend.copy()
		ret._printAreaHull = self._printAreaHull.copy()
		ret._drawOffset = self._drawOffset.copy()
		for m in self._meshList[:]:
			m2 = ret._addMesh()
			m2.vertexes = m.vertexes
			m2.vertexCount = m.vertexCount
			m2.vbo = m.vbo
			m2.vbo.incRef()
		return ret

	def _addMesh(self):
		m = Mesh()
		self._meshList.append(m)
		return m

	def _postProcessAfterLoad(self):
		for m in self._meshList:
			m._calculateNormals()
		self.processMatrix()
		#check if size is in a sensible range
		if numpy.max(self.getSize()) > 10000.0:
			for m in self._meshList:
				m.vertexes /= 1000.0
			self.processMatrix()
		if numpy.max(self.getSize()) < 1.0:
			for m in self._meshList:
				m.vertexes *= 1000.0
			self.processMatrix()

	def applyMatrix(self, m):
		self._matrix *= m
		self.processMatrix()

	def processMatrix(self):
		self._transformedMin = numpy.array([999999999999,999999999999,999999999999], numpy.float64)
		self._transformedMax = numpy.array([-999999999999,-999999999999,-999999999999], numpy.float64)
		self._boundaryCircleSize = 0

		hull = numpy.zeros((0, 2), numpy.int)
		for m in self._meshList:
			transformedVertexes = m.getTransformedVertexes()
			hull = polygon.convexHull(numpy.concatenate((numpy.rint(transformedVertexes[:,0:2]).astype(int), hull), 0))
			transformedMin = transformedVertexes.min(0)
			transformedMax = transformedVertexes.max(0)
			for n in xrange(0, 3):
				self._transformedMin[n] = min(transformedMin[n], self._transformedMin[n])
				self._transformedMax[n] = max(transformedMax[n], self._transformedMax[n])

			#Calculate the boundary circle
			transformedSize = transformedMax - transformedMin
			center = transformedMin + transformedSize / 2.0
			boundaryCircleSize = round(math.sqrt(numpy.max(((transformedVertexes[::,0] - center[0]) * (transformedVertexes[::,0] - center[0])) + ((transformedVertexes[::,1] - center[1]) * (transformedVertexes[::,1] - center[1])) + ((transformedVertexes[::,2] - center[2]) * (transformedVertexes[::,2] - center[2])))), 3)
			self._boundaryCircleSize = max(self._boundaryCircleSize, boundaryCircleSize)
		self._transformedSize = self._transformedMax - self._transformedMin
		self._drawOffset = (self._transformedMax + self._transformedMin) / 2
		self._drawOffset[2] = self._transformedMin[2]
		self._transformedMax -= self._drawOffset
		self._transformedMin -= self._drawOffset

		self._boundaryHull = polygon.minkowskiHull((hull.astype(numpy.float32) - self._drawOffset[0:2]), numpy.array([[-1,-1],[-1,1],[1,1],[1,-1]],numpy.float32))
		self._printAreaHull = polygon.minkowskiHull(self._boundaryHull, self._printAreaExtend)
		self.setHeadArea(self._headAreaExtend, self._headMinSize)

	def getName(self):
		return self._name
	def getOriginFilename(self):
		return self._originFilename
	def getPosition(self):
		return self._position
	def setPosition(self, newPos):
		self._position = newPos
	def getMatrix(self):
		return self._matrix

	def getMaximum(self):
		return self._transformedMax
	def getMinimum(self):
		return self._transformedMin
	def getSize(self):
		return self._transformedSize
	def getDrawOffset(self):
		return self._drawOffset
	def getBoundaryCircle(self):
		return self._boundaryCircleSize

	def setPrintAreaExtends(self, poly):
		self._printAreaExtend = poly
		self._printAreaHull = polygon.minkowskiHull(self._boundaryHull, self._printAreaExtend)

		self.setHeadArea(self._headAreaExtend, self._headMinSize)

	def setHeadArea(self, poly, minSize):
		self._headAreaExtend = poly
		self._headMinSize = minSize
		self._headAreaHull = polygon.minkowskiHull(self._printAreaHull, self._headAreaExtend)
		pMin = numpy.min(self._printAreaHull, 0) - self._headMinSize
		pMax = numpy.max(self._printAreaHull, 0) + self._headMinSize
		square = numpy.array([pMin, [pMin[0], pMax[1]], pMax, [pMax[0], pMin[1]]], numpy.float32)
		self._headAreaMinHull = polygon.clipConvex(self._headAreaHull, square)

	def mirror(self, axis):
		matrix = [[1,0,0], [0, 1, 0], [0, 0, 1]]
		matrix[axis][axis] = -1
		self.applyMatrix(numpy.matrix(matrix, numpy.float64))

	def getScale(self):
		return numpy.array([
			numpy.linalg.norm(self._matrix[::,0].getA().flatten()),
			numpy.linalg.norm(self._matrix[::,1].getA().flatten()),
			numpy.linalg.norm(self._matrix[::,2].getA().flatten())], numpy.float64);

	def setScale(self, scale, axis, uniform):
		currentScale = numpy.linalg.norm(self._matrix[::,axis].getA().flatten())
		scale /= currentScale
		if scale == 0:
			return
		if uniform:
			matrix = [[scale,0,0], [0, scale, 0], [0, 0, scale]]
		else:
			matrix = [[1.0,0,0], [0, 1.0, 0], [0, 0, 1.0]]
			matrix[axis][axis] = scale
		self.applyMatrix(numpy.matrix(matrix, numpy.float64))

	def setSize(self, size, axis, uniform):
		scale = self.getSize()[axis]
		scale = size / scale
		if scale == 0:
			return
		if uniform:
			matrix = [[scale,0,0], [0, scale, 0], [0, 0, scale]]
		else:
			matrix = [[1,0,0], [0, 1, 0], [0, 0, 1]]
			matrix[axis][axis] = scale
		self.applyMatrix(numpy.matrix(matrix, numpy.float64))

	def resetScale(self):
		x = 1/numpy.linalg.norm(self._matrix[::,0].getA().flatten())
		y = 1/numpy.linalg.norm(self._matrix[::,1].getA().flatten())
		z = 1/numpy.linalg.norm(self._matrix[::,2].getA().flatten())
		self.applyMatrix(numpy.matrix([[x,0,0],[0,y,0],[0,0,z]], numpy.float64))

	def resetRotation(self):
		x = numpy.linalg.norm(self._matrix[::,0].getA().flatten())
		y = numpy.linalg.norm(self._matrix[::,1].getA().flatten())
		z = numpy.linalg.norm(self._matrix[::,2].getA().flatten())
		self._matrix = numpy.matrix([[x,0,0],[0,y,0],[0,0,z]], numpy.float64)
		self.processMatrix()

	def layFlat(self):
		transformedVertexes = self._meshList[0].getTransformedVertexes()
		minZvertex = transformedVertexes[transformedVertexes.argmin(0)[2]]
		dotMin = 1.0
		dotV = None
		for v in transformedVertexes:
			diff = v - minZvertex
			len = math.sqrt(diff[0] * diff[0] + diff[1] * diff[1] + diff[2] * diff[2])
			if len < 5:
				continue
			dot = (diff[2] / len)
			if dotMin > dot:
				dotMin = dot
				dotV = diff
		if dotV is None:
			return
		rad = -math.atan2(dotV[1], dotV[0])
		self._matrix *= numpy.matrix([[math.cos(rad), math.sin(rad), 0], [-math.sin(rad), math.cos(rad), 0], [0,0,1]], numpy.float64)
		rad = -math.asin(dotMin)
		self._matrix *= numpy.matrix([[math.cos(rad), 0, math.sin(rad)], [0,1,0], [-math.sin(rad), 0, math.cos(rad)]], numpy.float64)


		transformedVertexes = self._meshList[0].getTransformedVertexes()
		minZvertex = transformedVertexes[transformedVertexes.argmin(0)[2]]
		dotMin = 1.0
		dotV = None
		for v in transformedVertexes:
			diff = v - minZvertex
			len = math.sqrt(diff[1] * diff[1] + diff[2] * diff[2])
			if len < 5:
				continue
			dot = (diff[2] / len)
			if dotMin > dot:
				dotMin = dot
				dotV = diff
		if dotV is None:
			return
		if dotV[1] < 0:
			rad = math.asin(dotMin)
		else:
			rad = -math.asin(dotMin)
		self.applyMatrix(numpy.matrix([[1,0,0], [0, math.cos(rad), math.sin(rad)], [0, -math.sin(rad), math.cos(rad)]], numpy.float64))

	def scaleUpTo(self, size):
		vMin = self._transformedMin
		vMax = self._transformedMax

		scaleX1 = (size[0] / 2 - self._position[0]) / ((vMax[0] - vMin[0]) / 2)
		scaleY1 = (size[1] / 2 - self._position[1]) / ((vMax[1] - vMin[1]) / 2)
		scaleX2 = (self._position[0] + size[0] / 2) / ((vMax[0] - vMin[0]) / 2)
		scaleY2 = (self._position[1] + size[1] / 2) / ((vMax[1] - vMin[1]) / 2)
		scaleZ = size[2] / (vMax[2] - vMin[2])
		scale = min(scaleX1, scaleY1, scaleX2, scaleY2, scaleZ)
		if scale > 0:
			self.applyMatrix(numpy.matrix([[scale,0,0],[0,scale,0],[0,0,scale]], numpy.float64))

	#Split splits an object with multiple meshes into different objects, where each object is a part of the original mesh that has
	# connected faces. This is useful to split up plate STL files.
	def split(self, callback):
		ret = []
		for oriMesh in self._meshList:
			ret += oriMesh.split(callback)
		return ret

	def canStoreAsSTL(self):
		return len(self._meshList) < 2

	#getVertexIndexList returns an array of vertexes, and an integer array for each mesh in this object.
	# the integer arrays are indexes into the vertex array for each triangle in the model.
	def getVertexIndexList(self):
		vertexMap = {}
		vertexList = []
		meshList = []
		for m in self._meshList:
			verts = m.getTransformedVertexes(True)
			meshIdxList = []
			for idx in xrange(0, len(verts)):
				v = verts[idx]
				hashNr = int(v[0] * 100) | int(v[1] * 100) << 10 | int(v[2] * 100) << 20
				vIdx = None
				if hashNr in vertexMap:
					for idx2 in vertexMap[hashNr]:
						if numpy.linalg.norm(v - vertexList[idx2]) < 0.001:
							vIdx = idx2
				if vIdx is None:
					vIdx = len(vertexList)
					vertexMap[hashNr] = [vIdx]
					vertexList.append(v)
				meshIdxList.append(vIdx)
			meshList.append(numpy.array(meshIdxList, numpy.int32))
		return numpy.array(vertexList, numpy.float32), meshList