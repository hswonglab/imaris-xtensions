#  ImportSurfaces: An Imaris XTension to export surfaces.
#
#  Copyright © 2023-2025 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Amy Huang. Based off of ExportSurfaces.py by Chris Skalnik. 
#
#    <CustomTools>
#      <Menu>
#       <Item name="Import Surfaces" icon="Python3" tooltip="Import surface objects.">
#         <Command>Python3XT::ImportSurfaces(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ImportSurfaces exports the surfaces in an Imaris file for use outside Imaris.
'''

import csv
import logging
import os
import sys
import traceback
from tqdm import tqdm

import ImarisLib
import Imaris
import orjson

from tkinter import Tk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import simpledialog

# Some DLLs are stored at this path, but it isn't correctly set by default. We
# can't just set the system environment variable because doing so adds a space
# at the end of the path for some reason. This means that instead of searching
# for \path\to\bin\myDll.dll, it searches for \path\to\bin\ myDll.dll.
DLL_PATH = os.path.join(os.path.dirname(sys.executable), 'Library', 'bin')
os.environ['PATH'] += f';{DLL_PATH}'

import numpy as np

LOG_FORMAT = '%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d %(name)s] %(message)s'

def Main(vImarisApplication):
    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    logging.basicConfig(format=LOG_FORMAT, filename=logpath, level=logging.INFO)
    logging.info('----- Begin importing surfaces to %s -----', image_path)

    # Get the image and channels
    vNumberOfImages = vImarisApplication.GetNumberOfImages()
    if vNumberOfImages != 1:
        messagebox.showwarning('Only 1 image may be open at a time for this XTension')
        return

    vSurfaces = vImarisApplication.GetFactory().CreateSurfaces()
    
    logging.info('Asking user to select json')
    vFilePath = filedialog.askopenfilename(title='Select json representing Imaris surfaces')
    if not vFilePath:
        return
    with open(vFilePath, 'rb') as f:
        vSurfaceJson = orjson.loads(f.read())

    # Determine global data type from max value across all masks (cheap scan)
    logging.info('Scanning %d surface masks for max value', len(vSurfaceJson))
    vGlobalMax = max(
        int(np.max(s['mask'])) for s in tqdm(vSurfaceJson, desc='Scanning max')
    )
    if vGlobalMax <= np.iinfo(np.uint8).max:
        vDtype = np.uint8
        vImarisType = Imaris.tType.eTypeUInt8
    elif vGlobalMax <= np.iinfo(np.uint16).max:
        vDtype = np.uint16
        vImarisType = Imaris.tType.eTypeUInt16
    else:
        vDtype = np.float32
        vImarisType = Imaris.tType.eTypeFloat
    logging.info('Global max mask value: %d, using type: %s', vGlobalMax, vImarisType)

    logging.info('Importing %d surfaces', len(vSurfaceJson))
    for vSurfaceJsonData in tqdm(vSurfaceJson, desc='Importing'):
        vData = np.ascontiguousarray(
            np.array(vSurfaceJsonData['mask'], dtype=vDtype).transpose([2, 1, 0])
        )
        vSurfaceJsonData['mask'] = None  # free JSON mask data
        vSizeX, vSizeY, vSizeZ = vData.shape

        # create aSurfaceData dataset
        aSurfaceData = vImarisApplication.GetFactory().CreateDataSet()
        aSurfaceData.Create(vImarisType, vSizeX, vSizeY, vSizeZ, 1, 1)
        # Use flat 1D array method — much faster than nested-list SetDataVolumeFloats
        aSurfaceData.SetDataVolumeAs1DArrayFloats(vData.flatten().tolist(), 0, 0)

        aSurfaceData.SetExtendMinX(vSurfaceJsonData['xRange'][0])
        aSurfaceData.SetExtendMaxX(vSurfaceJsonData['xRange'][1])

        aSurfaceData.SetExtendMinY(vSurfaceJsonData['yRange'][0])
        aSurfaceData.SetExtendMaxY(vSurfaceJsonData['yRange'][1])

        aSurfaceData.SetExtendMinZ(vSurfaceJsonData['zRange'][0])
        aSurfaceData.SetExtendMaxZ(vSurfaceJsonData['zRange'][1])

        # add aSurfaceData to Surfaces
        try:
            vSurfaces.AddSurface(aSurfaceData, 0) # second number is time index which is irrelevant
        except Exception as e:
            logging.warning(f'Failed to add surface:\n{e}')
            logging.warning(f'The skipped surface:\n{vData}')

    vSurfaces.SetName('Imported Surfaces')

    # add to scene
    vScene = vImarisApplication.GetSurpassScene()
    vScene.AddChild(vSurfaces, -1)

    logging.info(
        f'Imported %d surfaces',
        len(vSurfaceJson),
    )
    logging.info('----- Done importing surfaces -----')

def ImportSurfaces(aImarisId):
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
