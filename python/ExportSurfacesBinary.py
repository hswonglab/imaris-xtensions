#  ExportSurfacesBinary: An Imaris XTension to export surfaces.
#
#  Copyright © 2023-2025 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Christopher Skalnik.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Export Surfaces Binary" icon="Python3" tooltip="Export surface objects.">
#         <Command>Python3XT::ExportSurfacesBinary(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ExportSurfacesBinary exports the surfaces in an Imaris file for use outside Imaris.

Unlike ExportSurfaces, ExportSurfacesBinary exports to the binary JSON-like
messagepack format for a more compressed representation of surfaces.
'''

import datetime
import logging
from multiprocessing import get_context
import os
import sys
import time
import traceback

import ImarisLib

import msgpack
import orjson
from tkinter import Tk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import simpledialog
from tqdm import tqdm, trange

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


imaris_handling_context = get_context()

class ImarisDependentProcess(imaris_handling_context.Process):
    '''Process that will run a cleanup function before exiting.'''
    @staticmethod
    def teardown():
        # Assuming vImarisLib was setup with InitializeWorker().
        vImarisLib.Disconnect()

    def run(self):
        if self._target:
            self._target(*self._args, **self._kwargs)
            self.teardown()

imaris_handling_context.Process = ImarisDependentProcess


def InitializeWorker(aImarisId):
    '''Setup the calling worker with a connection to Imaris.'''
    # This initializer runs as each worker process is spun up, and the workers
    # will be destroyed once they finish, so global variables are okay here.
    global vImarisLib
    global vImarisApplication
    global vSurfaces

    vImarisLib = ImarisLib.ImarisLib()
    vImarisApplication = vImarisLib.GetApplication(aImarisId)
    vSurfaces = vImarisApplication.GetFactory().ToSurfaces(vImarisApplication.GetSurpassSelection())


def GetSurfacesJson(indices, ids):
    '''Retrieve JSON data representing multiple Surface objects.

    Meant to be run asynchronously as one task in a multiprocessing pool.'''
    surfaces_json = []
    for surface_index, surface_id in zip(indices, ids):
        surfaces_json.append(GetSurfaceJson(surface_index, surface_id))
    return surfaces_json


def GetSurfaceJson(vSurfaceIndex, vSurfaceId):
    '''Retrieve a Surface's JSON data.

    Meant to be run asynchronously as one task in a multiprocessing pool.'''
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

    vFlatSurfaceData = vSurfaceDataArray.flatten() > 0
    vBinarySurfaceData = np.packbits(vFlatSurfaceData, bitorder='big').tobytes()

    aSurfaceJson = {
        'id': vSurfaceId,
        # xRange, yRange, and zRange define the ranges of x, y, and z
        # coordinates spanned by the bounding box filled by the mask.
        'xRange': [vSurfaceData.GetExtendMinX(), vSurfaceData.GetExtendMaxX()],
        'yRange': [vSurfaceData.GetExtendMinY(), vSurfaceData.GetExtendMaxY()],
        'zRange': [vSurfaceData.GetExtendMinZ(), vSurfaceData.GetExtendMaxZ()],
        'maskShape': list(vSurfaceDataArray.shape),
        # The mask contains positive values inside the surface and negative
        # values outside the surface. To identify the precise boundary of
        # the surface, interpolate between the positive and negative values
        # to find the zero point. Alternatively, for an approximate mask,
        # binarize on the sign of each voxel. Mask dimensions are (z, y, x).
        'mask': vBinarySurfaceData,
    }
    return aSurfaceJson


def Main(vImarisApplication, aImarisId):
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
    start = time.time()
    print('Retrieving surface data')
    workers = min(os.cpu_count(), len(vSurfaceIds))
    # If num_tasks is the number of surfaces, then we operate like a typical
    # pool of workers where each task is to retrieve one surface. If num_tasks
    # is the number of workers, then each worker will only get one task, and we
    # operate as if instead of using a pool we pre-partitioned the tasks among
    # the workers.

    # Benchmarking with 1000 surfaces:
    # num_tasks = workers: 0.09237308502197265 min
    # num_tasks = num surfaces: 0.09286127090454102 min

    # Benchmarking with >158,000 surfaces:
    # num_tasks = workers: 29.60245312054952 min
    # num_tasks = num_surfaces: 24.2604834040006 min, 37 mins
    num_tasks = workers
    tasks = [([], []) for _ in range(num_tasks)]
    progressbar = tqdm(total=len(tasks))
    with imaris_handling_context.Pool(
        processes=workers,
        initializer=InitializeWorker,
        initargs=(aImarisId,),
    ) as pool:
        for i, (vSurfaceIndex, vSurfaceId) in enumerate(zip(vSurfaceIndices, vSurfaceIds)):
            tasks[i % num_tasks][0].append(vSurfaceIndex)
            tasks[i % num_tasks][1].append(vSurfaceId)
        results = [
            pool.apply_async(GetSurfacesJson, (task_indices, task_ids))
            for task_indices, task_ids in tasks
        ]
        done = 0
        while done < len(tasks):
            now_done = sum([res.ready() for res in results])
            progressbar.update(now_done - done)
            done = now_done
            time.sleep(1)
        vSurfaceJson = []
        for res in results:
            vSurfaceJson.extend(res.get(timeout=1))
    end = time.time()
    progressbar.close()
    print(f'Surfaces retrieved in {(end - start) / 60} min')

    vSafeSurfaceName = vSurfaces.GetName().replace(' ', '_')
    vExportPath = f'{os.path.splitext(image_path)[0]}-{vSafeSurfaceName}-benchmark.mpk'
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
    start = time.time()
    packed_data = msgpack.packb(vExportData, strict_types=True)
    blocksize = 1024 * 1024  # Write in 1 MiB chunks for progress bar.
    with open(vExportPath, 'wb') as f:
        for i in trange(0, len(packed_data), blocksize):
            f.write(packed_data[i:i + blocksize])
    end = time.time()
    print(f'Wrote surfaces in {(end - start) / 60} min')

    logging.info(
        f'Exported %d surfaces from set "%s" to "%s"',
        len(vSurfaceJson), vSurfaces.GetName(), vExportPath,
    )
    logging.info('----- Done exporting surfaces from %s -----', image_path)

def ExportSurfacesBinary(aImarisId):
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
        Main(vImarisApplication, aImarisId)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
