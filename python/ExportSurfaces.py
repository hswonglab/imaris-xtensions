#  ExportSurfaces: An Imaris XTension to export surfaces.
#
#  Copyright © 2023-2025 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Christopher Skalnik.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Export Surfaces" icon="Python3" tooltip="Export surface objects.">
#         <Command>Python3XT::ExportSurfaces(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ExportSurfaces exports the surfaces in an Imaris file for use outside Imaris.
'''

import datetime
import logging
import os
import sys
import traceback

import ImarisLib

import orjson
from tkinter import Tk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import simpledialog
from tqdm import tqdm

# Some DLLs that numpy needs are stored at this path, but it isn't correctly
# set by default. We can't just set the system environment variable because
# doing so adds a space at the end of the path for some reason. This means that
# instead of searching for \path\to\bin\myDll.dll, it searches for
# \path\to\bin\ myDll.dll.
DLL_PATH = os.path.join(os.path.dirname(sys.executable), 'Library', 'bin')
os.environ['PATH'] += f';{DLL_PATH}'

import numpy as np

LOG_FORMAT = '%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d %(name)s] %(message)s'
SURFACE_SERIALIZATION_SPEC_VERSION = "0.1.0"

def Main(vImarisApplication):
    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    logging.basicConfig(format=LOG_FORMAT, filename=logpath, level=logging.INFO)
    logging.info('----- Begin exporting surfaces from %s -----', image_path)

    # Get the image and channels
    vNumberOfImages = vImarisApplication.GetNumberOfImages()
    if vNumberOfImages != 1:
        messagebox.showwarning('Only 1 image may be open at a time for this XTension')
        return

    vSurfaces = vImarisApplication.GetFactory().ToSurfaces(vImarisApplication.GetSurpassSelection())
    logging.info('Selected set of surfaces: %s', vSurfaces.GetName())
    vNumSelected = len(vSurfaces.GetSelectedIndices())
    vSelectionMode = messagebox.askyesnocancel(
        'Surfaces Selection', 
        f'Export only the {vNumSelected} selected surfaces? Choose "No" to export all surfaces in "{vSurfaces.GetName()}".')
    if vSelectionMode is True:
        vSurfaceIndices = vSurfaces.GetSelectedIndices()
        vSurfaceIds = vSurfaces.GetSelectedIds()
        logging.info('Exporting only %d selected surfaces.', vNumSelected)
    elif vSelectionMode is False:
        vSurfaceIndices = range(vSurfaces.GetNumberOfSurfaces())
        vSurfaceIds = vSurfaces.GetIds()
        logging.info('Exporting all surfaces in selected set.')
    else:
        logging.info('User canceled when asked whether to export only selected surfaces.')
        return

    print(f'Exporting {len(vSurfaceIndices)} surfaces in "{vSurfaces.GetName()}".')

    vSurfaceJson = []
    for vSurfaceIndex, vSurfaceId in zip(tqdm(vSurfaceIndices), vSurfaceIds):
        vSurfaceData = vSurfaces.GetSurfaceData(vSurfaceIndex)
        assert str(vSurfaceData.GetType()) == 'eTypeUInt16'
        vSurfaceDataArray = np.array(vSurfaceData.GetDataFloats(), dtype='int16')
        # The data array is a 5-dimensional array. The first two dimensions
        # appear to be meaningless and have size 1. The last 3 dimensions are
        # x, y, and z.
        assert vSurfaceDataArray.shape[0] == 1
        assert vSurfaceDataArray.shape[1] == 1
        # Re-shape the data array to have axes (z, y, x).
        vSurfaceDataArray = vSurfaceDataArray[0, 0, :, :, :].transpose([2, 1, 0])

        vSurfaceJson.append({
            'id': vSurfaceId,
            # xRange, yRange, and zRange define the ranges of x, y, and z
            # coordinates spanned by the bounding box filled by the mask.
            'xRange': [vSurfaceData.GetExtendMinX(), vSurfaceData.GetExtendMaxX()],
            'yRange': [vSurfaceData.GetExtendMinY(), vSurfaceData.GetExtendMaxY()],
            'zRange': [vSurfaceData.GetExtendMinZ(), vSurfaceData.GetExtendMaxZ()],
            # The mask contains positive values inside the surface and negative
            # values outside the surface. To identify the precise boundary of
            # the surface, interpolate between the positive and negative values
            # to find the zero point. Alternatively, for an approximate mask,
            # binarize on the sign of each voxel. Mask dimensions are (z, y, x).
            'mask': vSurfaceDataArray.tolist(),
        })
    vSafeSurfaceName = vSurfaces.GetName().replace(' ', '_')
    vExportPath = f'{os.path.splitext(image_path)[0]}-{vSafeSurfaceName}.json'
    if os.path.exists(vExportPath):
        logging.info(f'Existing file detected at {vExportPath}. Asking user for confirmation.')
        if messagebox.askyesno(
            'Overwrite warning',
            f'Export destination "{vExportPath}" already exists. Overwrite?'
        ):
            logging.info('User chose to overwrite. Exporting.')
        else:
            logging.info('User declined to overwrite. Aborting.')
            return
    vExportData = {
        'version': SURFACE_SERIALIZATION_SPEC_VERSION,
        'metadata': {
            'sourceImage': image_path,
            'sourceSurface': vSurfaces.GetName(),
            'sourceSoftware': vImarisApplication.GetVersion(),
            'exportDateTime': datetime.datetime.now(
                datetime.timezone.utc).isoformat()
        },
        'surfaces': vSurfaceJson,
    }
    print(f'Writing export to {vExportPath}')
    with open(vExportPath, 'wb') as f:
        f.write(orjson.dumps(vExportData, option=orjson.OPT_SERIALIZE_NUMPY))

    logging.info(
        f'Exported %d surfaces from set "%s" to "%s"',
        len(vSurfaceJson), vSurfaces.GetName(), vExportPath,
    )
    logging.info('----- Done exporting surfaces from %s -----', image_path)

def ExportSurfaces(aImarisId):
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
        # Note that if you want to profile this tool's runtime, un-comment the
        # line below. You must also temporarly stop using tqdm to get an
        # accurate profile.
        #cProfile.runctx('Main(vImarisApplication)', globals=globals(), locals=locals(), filename='stats')
        Main(vImarisApplication)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
