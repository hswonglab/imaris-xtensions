#  ImportSurfacesChunked: An Imaris XTension to import surfaces (chunked).
#
#  Copyright © 2023-2026 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Amy Huang. Based off of ImportSurfaces.py.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Import Surfaces (Chunked)" icon="Python3" tooltip="Import surface objects using chunked ISurfaces containers for speed.">
#         <Command>Python3XT::ImportSurfacesChunked(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ImportSurfacesChunked imports surfaces into Imaris the same way
ImportSurfaces does, but splits the surface set across multiple ISurfaces
containers instead of adding every surface to a single one.

Why: ImageImportSurfaces() in ImportSurfaces.py calls AddSurface() on one
ISurfaces object once per surface. Import throughput drops off nonlinearly as
that single container accumulates surfaces (measured effective exponent
~1.7 on n=10,000..40,726), so a 100k+ surface set takes much longer per-
surface near the end of the import than at the start. This version adds
surfaces to a rotating set of smaller ISurfaces containers ("chunks") instead
of one large one, then groups the chunks under a single Group node in the
Surpass scene so they still present as one named item.

Speed-test history 
  n=10,000,  chunk_size=1000: chunked is ~42.5% faster than the original.
  n=40,726,  chunk_size=1000: chunked is ~78.2% faster than the original
             (~4.6x speedup). The chunked advantage grows sharply with n,
             consistent with the original's per-item cost degrading faster
             than linearly as its single container grows.

This module was promoted from ImportSurfaces_beta.py once the above results
confirmed the chunked approach's advantage at production scale. It is kept
as a separate menu item/module from ImportSurfaces.py (rather than merged
in) so the two can still be run back-to-back for comparison and so any
regressions are isolated to one file.

Setting the chunk size >= the number of surfaces in the file reduces this
script to (almost) the same behavior as the non-chunked version, which makes
it useful as an apples-to-apples baseline too.
'''
try:
    import logging
    import math
    import os
    import sys
    import time
    import traceback
    from tqdm import tqdm

    import ImarisLib
    import Imaris
    import orjson

    from tkinter import Tk
    from tkinter import messagebox
    from tkinter import filedialog
    from tkinter import simpledialog
    from XTBatch import XTBatch
except Exception as e:
    print(e)
    input("Press enter to exit;")
    raise

# Some DLLs are stored at this path, but it isn't correctly set by default. We
# can't just set the system environment variable because doing so adds a space
# at the end of the path for some reason. This means that instead of searching
# for \path\to\bin\myDll.dll, it searches for \path\to\bin\ myDll.dll.
DLL_PATH = os.path.join(os.path.dirname(sys.executable), 'Library', 'bin')
os.environ['PATH'] += f';{DLL_PATH}'

import numpy as np

LOG_FORMAT = '%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d %(name)s] %(message)s'

# Number of surfaces to add to any one ISurfaces container before rolling over
# to a fresh one. chunk_size=1000 is the value validated so far (see the
# speed-test history above); a chunk-size sweep is planned to check whether a
# different value does even better. Update this default once that sweep
# picks a winner.
DEFAULT_CHUNK_SIZE = 1000


class TqdmStreamHandler(logging.StreamHandler):
    """StreamHandler that writes through tqdm.write() to avoid breaking progress bars."""
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=self.stream)
            self.flush()
        except Exception:
            self.handleError(record)


def Main_Chunked(vImarisApplication):
    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    logging.basicConfig(
        format=LOG_FORMAT,
        level=logging.INFO,
        handlers=[
            logging.FileHandler(logpath),
            TqdmStreamHandler(sys.stdout),
        ]
    )

    # Get the image and channels
    vNumberOfImages = vImarisApplication.GetNumberOfImages()
    if vNumberOfImages != 1:
        messagebox.showwarning('Only 1 image may be open at a time for this XTension')
        return

    logging.info('Asking user to select json')
    vFilePath = filedialog.askopenfilename(title='Select json representing Imaris surfaces')
    if not vFilePath:
        return

    vSurfaceName = simpledialog.askstring(
        'Surface Name', 'Enter name for imported surfaces:',
        initialvalue='Imported Surfaces'
    ) or 'Imported Surfaces'

    vChunkSize = simpledialog.askinteger(
        'Chunk Size',
        'Number of surfaces per ISurfaces container before starting a new one.\n'
        'Set this to a number >= the total surface count to disable chunking\n'
        '(i.e. behave like the non-chunked ImportSurfaces script):',
        initialvalue=DEFAULT_CHUNK_SIZE, minvalue=1,
    )
    if vChunkSize is None:
        return

    batched = messagebox.askyesno(
        'Batched Operation.',
        'Would you like to apply changes to all .ims files in this folder?  \n' \
        'If yes, the name of the selected .json file must begin with the name of the selected .ims file.'
    )

    if batched:
        vBase, _ = os.path.splitext(image_path)
        vFilePath = vFilePath.replace('/', '\\')
        if vFilePath[:len(vBase)] == vBase:
            json_suffix = vFilePath[len(vBase):]
            image_folder_path = '\\'.join(image_path.split('\\')[:-1])
        else:
            raise Exception('Name of selected .json file does not begin with the name of the selected .ims file.')
        XTBatch(vImarisApplication, fn=ImageImportSurfacesChunked, args=(vSurfaceName, vChunkSize),
                im_args_func=lambda FileName: (image_folder_path + '\\' + FileName + json_suffix,), operate_on_image=False)
    else:
        ImageImportSurfacesChunked(vImarisApplication, vSurfaceName, vChunkSize, vFilePath)
        # Save to a new file with suffix — I can't make Imaris overwrite the currently open file
        vBase, vExt = os.path.splitext(image_path)
        vSavePath = f'{vBase}-imported_surfaces_chunked{vExt}'
        logging.info('Saving to %s', vSavePath)
        vImarisApplication.FileSave(vSavePath, '')

    logging.info('----- Begin importing surfaces to %s -----', image_path)
    logging.info('----- Done importing surfaces -----')


def ImageImportSurfacesChunked(vImarisApplication, vSurfaceName, vChunkSize, vFilePath):
    vStartTime = time.time()
    with open(vFilePath, 'rb') as f:
        vSurfaceJson = orjson.loads(f.read())

    vTotal = len(vSurfaceJson)
    vNumChunks = max(1, math.ceil(vTotal / vChunkSize))
    logging.info(
        'Importing %d surfaces in %d chunk(s) of up to %d surfaces each',
        vTotal, vNumChunks, vChunkSize,
    )

    n_skipped = 0
    vChunkSurfacesList = []
    vChunkTimings = []

    for vChunkIndex in range(vNumChunks):
        vChunkStartTime = time.time()
        vChunkStart = vChunkIndex * vChunkSize
        vChunkEnd = min(vChunkStart + vChunkSize, vTotal)
        vChunkJson = vSurfaceJson[vChunkStart:vChunkEnd]

        vSurfaces = vImarisApplication.GetFactory().CreateSurfaces()

        for vSurfaceJsonData in tqdm(
            vChunkJson, desc=f'Importing chunk {vChunkIndex + 1}/{vNumChunks}'
        ):
            vData = np.array(vSurfaceJsonData['mask'], dtype=np.uint16).transpose([2, 1, 0])
            vSurfaceJsonData['mask'] = None  # free JSON mask data
            vSizeX, vSizeY, vSizeZ = vData.shape

            # create aSurfaceData dataset
            aSurfaceData = vImarisApplication.GetFactory().CreateDataSet()
            aSurfaceData.Create(Imaris.tType.eTypeUInt16, vSizeX, vSizeY, vSizeZ, 1, 1)
            aSurfaceData.SetDataVolumeFloats(vData.tolist(), aIndexC=0, aIndexT=0)

            aSurfaceData.SetExtendMinX(vSurfaceJsonData['xRange'][0])
            aSurfaceData.SetExtendMaxX(vSurfaceJsonData['xRange'][1])

            aSurfaceData.SetExtendMinY(vSurfaceJsonData['yRange'][0])
            aSurfaceData.SetExtendMaxY(vSurfaceJsonData['yRange'][1])

            aSurfaceData.SetExtendMinZ(vSurfaceJsonData['zRange'][0])
            aSurfaceData.SetExtendMaxZ(vSurfaceJsonData['zRange'][1])

            # add aSurfaceData to this chunk's Surfaces container
            try:
                vSurfaces.AddSurface(aSurfaceData, 0)  # second number is time index which is irrelevant
            except Exception as e:
                logging.warning(f'Failed to add surface:\n{e}')
                logging.warning(f'The skipped surface:\n{vData}')
                n_skipped += 1

        vChunkName = vSurfaceName if vNumChunks == 1 else f'{vSurfaceName} [{vChunkIndex + 1}/{vNumChunks}]'
        vSurfaces.SetName(vChunkName)
        vChunkSurfacesList.append(vSurfaces)

        vChunkElapsed = time.time() - vChunkStartTime
        vChunkCount = len(vChunkJson)
        vChunkTimings.append((vChunkCount, vChunkElapsed))
        logging.info(
            'Chunk %d/%d: added %d surfaces in %.2f minutes (%.3f sec/surface)',
            vChunkIndex + 1, vNumChunks, vChunkCount, vChunkElapsed / 60,
            vChunkElapsed / vChunkCount if vChunkCount else 0.0,
        )

    # Add to scene. If there's more than one chunk, group them under a single
    # named Group node so the chunked import still presents as one item, the
    # same way the non-chunked version does.
    vScene = vImarisApplication.GetSurpassScene()
    if vNumChunks == 1:
        vScene.AddChild(vChunkSurfacesList[0], -1)
    else:
        vGroup = vImarisApplication.GetFactory().CreateDataContainer()
        vGroup.SetName(vSurfaceName)
        for vChunkSurfaces in vChunkSurfacesList:
            vGroup.AddChild(vChunkSurfaces, -1)
        vScene.AddChild(vGroup, -1)

    vElapsedTime = (time.time() - vStartTime) / 60
    logging.info(
        'Imported %d/%d surfaces (%d skipped) in %.2f minutes across %d chunk(s)',
        vTotal - n_skipped, vTotal, n_skipped, vElapsedTime, vNumChunks,
    )
    for vChunkNum, (vChunkCount, vChunkElapsed) in enumerate(vChunkTimings, start=1):
        logging.info(
            '  chunk %d: %d surfaces, %.2f min, %.3f sec/surface',
            vChunkNum, vChunkCount, vChunkElapsed / 60,
            vChunkElapsed / vChunkCount if vChunkCount else 0.0,
        )


def ImportSurfacesChunked(aImarisId):
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
        Main_Chunked(vImarisApplication)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')
