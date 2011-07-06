#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    Copyright 2010, 2011 C Sommer, C Straehle, U Koethe, FA Hamprecht. All rights reserved.
#    
#    Redistribution and use in source and binary forms, with or without modification, are
#    permitted provided that the following conditions are met:
#    
#       1. Redistributions of source code must retain the above copyright notice, this list of
#          conditions and the following disclaimer.
#    
#       2. Redistributions in binary form must reproduce the above copyright notice, this list
#          of conditions and the following disclaimer in the documentation and/or other materials
#          provided with the distribution.
#    
#    THIS SOFTWARE IS PROVIDED BY THE ABOVE COPYRIGHT HOLDERS ``AS IS'' AND ANY EXPRESS OR IMPLIED
#    WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
#    FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE ABOVE COPYRIGHT HOLDERS OR
#    CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#    CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#    SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
#    ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#    NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
#    ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#    
#    The views and conclusions contained in the software and documentation are those of the
#    authors and should not be interpreted as representing official policies, either expressed
#    or implied, of their employers.

from PyQt4.QtCore import pyqtSignal, QObject, QThread, Qt, QSize, QPointF, QRectF, \
                         QRect, QPoint
from PyQt4.QtGui  import QWidget, QPen, QGraphicsScene, QColor, QGraphicsLineItem, \
                         QImage, QPainter, QGraphicsLineItem

from ilastikdeps.core.volume import DataAccessor

import numpy
import threading
import time

from collections import deque

def is2D(shape5D):
    assert(len(shape5D) == 5)
    return shape5D[1] == 1 
def is3D(shape5D):
    assert(len(shape5D) == 5)
    return shape5D[1] > 1

#*******************************************************************************
# I m a g e W i t h P r o p e r t i e s                                        *
#*******************************************************************************

class ImageWithProperties(DataAccessor):
    """adds some nice properties to the image"""
    
    def __init__(self, dataAccessor):
        DataAccessor.__init__(self, dataAccessor)
    
    def is2D(self):
        return self.shape[1] == 1
    
    def is3D(self):
        return self.shape[1] > 1

#*******************************************************************************
# I n t e r a c t i o n L o g g e r                                            *
#*******************************************************************************

class InteractionLogger():
    #singleton pattern
    _instance = None
    _interactionLog = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(InteractionLogger, cls).__new__(cls, *args, **kwargs)
        return cls._instance
    
    def __init__(self):
        InteractionLogger._interactionLog = []
    
    @staticmethod
    def log(logEntry):
        if InteractionLogger._interactionLog != None:
            InteractionLogger._interactionLog.append(logEntry)

#*******************************************************************************
# S t a t e                                                                    *
#*******************************************************************************

class State():
    """abstract base class for undo redo stuff"""
    def __init__(self):
        pass

    def restore(self):
        pass

#*******************************************************************************
# L a b e l S t a t e                                                          *
#*******************************************************************************

class LabelState(State):
    def __init__(self, title, axis, num, offsets, shape, timeAxis, volumeEditor, erasing, labels, labelNumber):
        self.title = title
        self.time = timeAxis
        self.num = num
        self.offsets = offsets
        self.axis = axis
        self.erasing = erasing
        self.labelNumber = labelNumber
        self.labels = labels
        self.clock = time.clock()
        self.dataBefore = volumeEditor.drawManager.drawOnto.getSubSlice(self.offsets, self.labels.shape, self.num, self.axis, self.time, 0).copy()
        
    def restore(self, volumeEditor):
        temp = volumeEditor.drawManager.drawOnto.getSubSlice(self.offsets, self.labels.shape, self.num, self.axis, self.time, 0).copy()
        restore  = numpy.where(self.labels > 0, self.dataBefore, 0)
        stuff = numpy.where(self.labels > 0, self.dataBefore + 1, 0)
        erase = numpy.where(stuff == 1, 1, 0)
        self.dataBefore = temp
        #volumeEditor.labels._data.setSubSlice(self.offsets, temp, self.num, self.axis, self.time, 0)
        volumeEditor.setLabels(self.offsets, self.axis, self.num, restore, False)
        volumeEditor.setLabels(self.offsets, self.axis, self.num, erase, True)
        if volumeEditor.sliceSelectors[self.axis].value() != self.num:
            volumeEditor.sliceSelectors[self.axis].setValue(self.num)
        self.erasing = not(self.erasing)          

#*******************************************************************************
# H i s t o r y M a n a g e r                                                  *
#*******************************************************************************

class HistoryManager(QObject):
    def __init__(self, parent, maxSize = 3000):
        QObject.__init__(self)
        self.volumeEditor = parent
        self.maxSize = maxSize
        self._history = []
        self.current = -1

    def append(self, state):
        if self.current + 1 < len(self._history):
            self._history = self._history[0:self.current+1]
        self._history.append(state)

        if len(self._history) > self.maxSize:
            self._history = self._history[len(self._history)-self.maxSize:len(self._history)]
        
        self.current = len(self._history) - 1

    def undo(self):
        if self.current >= 0:
            self._history[self.current].restore(self.volumeEditor)
            self.current -= 1

    def redo(self):
        if self.current < len(self._history) - 1:
            self._history[self.current + 1].restore(self.volumeEditor)
            self.current += 1
            
    def serialize(self, grp, name='_history'):
        histGrp = grp.create_group(name)
        for i, hist in enumerate(self._history):
            histItemGrp = histGrp.create_group('%04d'%i)
            histItemGrp.create_dataset('labels',data=hist.labels)
            histItemGrp.create_dataset('axis',data=hist.axis)
            histItemGrp.create_dataset('slice',data=hist.num)
            histItemGrp.create_dataset('labelNumber',data=hist.labelNumber)
            histItemGrp.create_dataset('offsets',data=hist.offsets)
            histItemGrp.create_dataset('time',data=hist.time)
            histItemGrp.create_dataset('erasing',data=hist.erasing)
            histItemGrp.create_dataset('clock',data=hist.clock)

    def removeLabel(self, number):
        tobedeleted = []
        for index, item in enumerate(self._history):
            if item.labelNumber != number:
                item.dataBefore = numpy.where(item.dataBefore == number, 0, item.dataBefore)
                item.dataBefore = numpy.where(item.dataBefore > number, item.dataBefore - 1, item.dataBefore)
                item.labels = numpy.where(item.labels == number, 0, item.labels)
                item.labels = numpy.where(item.labels > number, item.labels - 1, item.labels)
            else:
                tobedeleted.append(index - len(tobedeleted))
                if index <= self.current:
                    self.current -= 1

        for val in tobedeleted:
            it = self._history[val]
            self._history.__delitem__(val)
            del it
            
    def clear(self):
        self._history = []

#*******************************************************************************
# V o l u m e U p d a t e                                                      *
#*******************************************************************************

class VolumeUpdate():
    def __init__(self, data, offsets, sizes, erasing):
        self.offsets = offsets
        self._data = data
        self.sizes = sizes
        self.erasing = erasing
    
    def applyTo(self, dataAcc):
        offsets = self.offsets
        sizes = self.sizes
        #TODO: move part of function into DataAccessor class !! e.g. setSubVolume or something
        tempData = dataAcc[offsets[0]:offsets[0]+sizes[0],\
                           offsets[1]:offsets[1]+sizes[1],\
                           offsets[2]:offsets[2]+sizes[2],\
                           offsets[3]:offsets[3]+sizes[3],\
                           offsets[4]:offsets[4]+sizes[4]].copy()

        if self.erasing == True:
            tempData = numpy.where(self._data > 0, 0, tempData)
        else:
            tempData = numpy.where(self._data > 0, self._data, tempData)
        
        dataAcc[offsets[0]:offsets[0]+sizes[0],\
                offsets[1]:offsets[1]+sizes[1],\
                offsets[2]:offsets[2]+sizes[2],\
                offsets[3]:offsets[3]+sizes[3],\
                offsets[4]:offsets[4]+sizes[4]] = tempData