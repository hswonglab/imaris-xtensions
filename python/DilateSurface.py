#  DilateSurface: An Imaris XTension to dilate surfaces.
#
#  Copyright © 2023-2026 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Christopher Skalnik.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Dilate Surface" icon="Python3" tooltip="Dilate surface objects.">
#         <Command>Python3XT::DilateSurface(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''DilateSurface dilates a surface in Imaris by a user-specified distance.

Dilation is performed by expanding the surface's bounding box in all directions
by the user-specified distance.

Whenever this XTension operates on a file, it tracks all changes in a log file.
If the file being modified is at path `path`, then the log file is at
`path.txt`. Note however that this XTension cannot save changes to the file, so
logged changes may not actually be saved if the user chooses not to.
'''

import csv
import logging
import os
import sys
import traceback

import ImarisLib

from tkinter import Tk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import simpledialog
from tqdm import tqdm

# Some DLLs are stored at this path, but it isn't correctly set by default. We
# can't just set the system environment variable because doing so adds a space
# at the end of the path for some reason. This means that instead of searching
# for \path\to\bin\myDll.dll, it searches for \path\to\bin\ myDll.dll.
DLL_PATH = os.path.join(os.path.dirname(sys.executable), 'Library', 'bin')
os.environ['PATH'] += f';{DLL_PATH}'

import numpy as np

EXPECTED_HEADER = ['channel', 'setting', 'fluorophore', 'target', 'color']
LOG_FORMAT = '%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d %(name)s] %(message)s'

def Main(vImarisApplication):
    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    logging.basicConfig(format=LOG_FORMAT, filename=logpath, level=logging.INFO)
    logging.info('----- Begin Editing %s -----', image_path)

    # Get the image and channels
    vNumberOfImages = vImarisApplication.GetNumberOfImages()
    if vNumberOfImages != 1:
        messagebox.showwarning('Only 1 image may be open at a time for this XTension')
        return

    vSurfaces = vImarisApplication.GetFactory().CreateSurfaces()
    vSurfaces = vImarisApplication.GetFactory().ToSurfaces(vImarisApplication.GetSurpassSelection())
    logging.info('Selected set of surfaces: %s', vSurfaces.GetName())
    vNumSelected = len(vSurfaces.GetSelectedIndices())
    vSelectionMode = messagebox.askyesnocancel(
        'Surfaces Selection', 
        f'Dilate only the {vNumSelected} selected surfaces? Choose "No" to dilate all surfaces in "{vSurfaces.GetName()}".')
    if vSelectionMode is True:
        vSurfaceIndices = vSurfaces.GetSelectedIndices()
        logging.info('Dilating only %d selected surfaces.', vNumSelected)
    elif vSelectionMode is False:
        vSurfaceIndices = range(vSurfaces.GetNumberOfSurfaces())
        logging.info('Dilating all surfaces in selected set.')
    else:
        logging.info('User canceled when asked whether to dilate only selected surfaces.')
        return

    print(f'Dilating {len(vSurfaceIndices)} surfaces in "{vSurfaces.GetName()}".')
    vDilationWidth = simpledialog.askfloat('Dilation Width', f'Distance (um) to dilate "{vSurfaces.GetName()}" by:')
    if vDilationWidth is None:
        logging.info('User canceled when asked for dilation width. Aborting.')
        return

    vNewSurfaces = vSurfaces.CopySurfaces([])  # Empty Surfaces object
    assert vNewSurfaces.GetNumberOfSurfaces() == 0
    for vSurfaceIndex in tqdm(vSurfaceIndices):
        vSurfaceData = vSurfaces.GetSurfaceData(vSurfaceIndex)
        assert str(vSurfaceData.GetType()) == 'eTypeUInt16'
        vSurfaceDataArray = np.array(vSurfaceData.GetDataFloats(), dtype='int16')
        # The data array is a 5-dimensional array. The first two dimensions
        # appear to be meaningless and have size 1. The last 3 dimensions are
        # x, y, and z.
        assert vSurfaceDataArray.shape[0] == 1
        assert vSurfaceDataArray.shape[1] == 1
        vTime = vSurfaces.GetTimeIndex(vSurfaceIndex)

        # I will expand surfaces simply by expanding their bounding boxes as
        # specified by SetExtend* functions.
        vNewSurfaceDataArray = vSurfaceDataArray.copy()
        vNewSurfaceData = vImarisApplication.GetFactory().CreateDataSet()
        vNewSurfaceData.Create(
            vSurfaceData.GetType(),
            vSurfaceData.GetSizeX(),
            vSurfaceData.GetSizeY(),
            vSurfaceData.GetSizeZ(),
            vSurfaceData.GetSizeC(),
            vSurfaceData.GetSizeT(),
        )
        vNewSurfaceData.SetExtendMinX(vSurfaceData.GetExtendMinX() - vDilationWidth)
        vNewSurfaceData.SetExtendMaxX(vSurfaceData.GetExtendMaxX() + vDilationWidth)
        vNewSurfaceData.SetExtendMinY(vSurfaceData.GetExtendMinY() - vDilationWidth)
        vNewSurfaceData.SetExtendMaxY(vSurfaceData.GetExtendMaxY() + vDilationWidth)
        vNewSurfaceData.SetExtendMinZ(vSurfaceData.GetExtendMinZ() - vDilationWidth)
        vNewSurfaceData.SetExtendMaxZ(vSurfaceData.GetExtendMaxZ() + vDilationWidth)

        vNewSurfaceData.SetDataFloats(vNewSurfaceDataArray.astype('uint16').tolist())
        vNewSurfaces.AddSurface(vNewSurfaceData, vTime)
    assert vNewSurfaces.GetNumberOfSurfaces() == len(vSurfaceIndices)
    vNewSurfaces.SetName(f'{vSurfaces.GetName()} Dilated by {vDilationWidth} um')
    logging.info(f'Dilated surfaces set "%s" by %f um', vSurfaces.GetName(), vDilationWidth)
    vNewSurfaces.SetColorRGBA(vSurfaces.GetColorRGBA())
    vSurfaces.GetParent().AddChild(vNewSurfaces, -1)
    logging.info('----- Done Editing %s -----', image_path)

def DilateSurface(aImarisId):
    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = Tk()
    vRootTkWindow.withdraw()

    # Check if the object is valid
    if vImarisApplication is None:
        messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return

    print(f'Connected to Imaris application (id={aImarisId})')

    try:
        Main(vImarisApplication)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
