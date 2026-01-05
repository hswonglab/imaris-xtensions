#  LinearUnmixing: An Imaris XTension to apply linear unmixing to an image
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Eric Gai.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Linear Unmixing" icon="Python3" tooltip="Linear Unmixing for Multiplexing">
#         <Command>Python3XT::LinearUnmixing(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''LinearUnmixing performs unmixing using a predefined compensation matrix.

The matrix should be provided as a .csv file. A square matrix of dimension 
equal to the number of channels in the image is expected. Each row of the matrix
is intended to represent a fluorophore and each column a 
detection channel. The ith column is intended to correspond to the principal detection
channel of the ith fluorophore. All diagonal entries would be unity, The (i,j)th
element of the matrix would indicate the signal of fluorophore i in 
detection channel j relative to the principal detection channel. All entries of 
the matrix would be between zero and one. The matrix will generally be 
asymmetric. Unmixing is performed by calculating the pseudoinverse of the 
compensation matrix and applying it to each pixel of the image.

This XTension supports batch operations. The user will be prompted to choose 
whether all .ims files in the directory of the current image shall be modified. 

Whenever this XTension operates on a file, it tracks all changes in a log file.
If the file currently opened is at path `path`, then the log file is at
`path.txt`. When called in batch mode, all logs will be written in `path.txt` 
corresponding to the file from which the XTension was called. 

This XTension will only save changes when run in batch mode. Otherwise, 
logged changes may not actually be saved if the user chooses not to.
'''

try:
    import csv
    import logging
    import traceback
    import ImarisLib
    from XTBatch import XTBatch
    from tkinter import *
    from tkinter import messagebox
    from tkinter import filedialog
    import numpy as np
    from tqdm.contrib.itertools import product
except Exception as e:
    print(e)
    input("Press enter to exit;")
    raise




LOG_FORMAT = '%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d %(name)s] %(message)s'

def Main(aImarisId):
    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Check if the object is valid
    if vImarisApplication is None:
        messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return
    
    print(f'Connected to Imaris application (id={aImarisId})')

    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    
    logging.basicConfig(format=LOG_FORMAT, filename=logpath, level=logging.INFO)
    logging.info('----- Begin Editing %s -----', image_path)

    with filedialog.askopenfile(mode='r', title='Select CSV specifying compensation matrix') as f:
        logging.info('Using compensation matrix from %s', f.name)
        reader = csv.reader(f)
        matrix = []
        for row in reader:
            matrix.append(row)
    matrix=np.array(matrix,dtype=np.float32)
    if matrix.shape[0] != matrix.shape[1]:
        raise RuntimeError(
            f'Number of rows in compensation matrix ({matrix.shape[0]}) '
            f'does not match number of columns ({matrix.shape[1]})'
        )
    
    logging.info('Calculating unmixing matrix.')
    unmixing_matrix=np.linalg.pinv(matrix)


    batched=messagebox.askyesno(
        'Batched Operation.',
        'Would you like to apply changes to all .ims files in this folder?'
    )

    if batched:
        XTBatch(vImarisApplication,ImageLinearUnmixing,(unmixing_matrix,))
    else:
        # Get the image and channels
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return

        vImage = vImarisApplication.GetImage(0)
        vImageNew=ImageLinearUnmixing(vImage,unmixing_matrix)
        vImarisApplication.SetImage(0, vImageNew)
        logging.info('Asking user to save image.')
        saved = messagebox.askyesno(
            'Save changes.',
            'Please save or discard changes. Did you save the file?'
        )
        logging.info('User reports that they saved changes: %s', saved)
        logging.info('----- Done Editing %s -----', image_path)
    print('Changes complete.')

def ImageLinearUnmixing(vImage,unmixing_matrix):

    vNumChannels = vImage.GetSizeC()
    vNumSlices = vImage.GetSizeZ()
    vXSize = vImage.GetSizeX()
    vYSize=vImage.GetSizeY()

    if unmixing_matrix.shape[0] != vNumChannels:
        raise RuntimeError(
            f'Number of rows in compensation matrix ({unmixing_matrix.shape[0]}) '
            f'does not match number of channels in image ({vNumChannels})'
        )


    logging.info('Unmixing image.')
    vImageNew = vImage.Clone()
    #process data slice by slice in square windows of length vWindowSize pixels
    vWindowSize = 10000 # larger windows can speed up execution but will be more memory-intensive
    for x,y,z in product(range(0,vXSize,vWindowSize),range(0,vYSize,vWindowSize),range(vNumSlices)):
        window_x_len=min(vWindowSize,vXSize-x)
        window_y_len=min(vWindowSize,vYSize-y)
        vImageArray=np.zeros((window_x_len,window_y_len,vNumChannels)) # container for subslice of image as numpy array
        for c in range(vNumChannels): # write each channel of image to array
            vImageArray[:,:,c]=np.array([np.frombuffer(row,dtype=np.uint8) for row in vImage.GetDataSubSliceBytes(aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=c,aIndexT=0,aSizeX=window_x_len,aSizeY=window_y_len)])
        vImageArrayUnmixed=np.uint8(np.matmul(vImageArray,unmixing_matrix).clip(0,255)) #apply matrix unmixing, truncate values below zero or above 255, and convert to integer format
        # np.uint8 returns an array with floor applied element-wise. rounding by np.rint does not appear to obviously affect the unmixed image and slows down the code slightly
        #TODO: compatibility for 16bit and 32bit images
        for c in range(vNumChannels): #write each channel of array to new image
            vImageNew.SetDataSubSliceBytes(aData=[row.tobytes() for row in vImageArrayUnmixed[:,:,c]],aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=c,aIndexT=0)
    logging.info('Unmixing complete.')
    return vImageNew


def LinearUnmixing(aImarisId):
    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = Tk()
    vRootTkWindow.withdraw()

    try:
        Main(aImarisId)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    messagebox.showinfo('Complete', 'The XTension has terminated.')

    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()


    ## get an imaris object with id aimarisid
    #vimarisapplication = vimarislib.getapplication(aimarisid)

    ## initialize and launch tk window, then hide it.
    #vroottkwindow = tk()
    #vroottkwindow.withdraw()

    ## check if the object is valid
    #if vimarisapplication is none:
    #    messagebox.showerror('error', f'failed to connect to imaris application (id={aimarisid})')
    #    return

    #print(f'connected to imaris application (id={aimarisid})')

    #try:
    #    main(vimarisapplication)
    #except exception as exception:
    #    print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    #messagebox.showinfo('complete', 'the xtension has terminated.')

