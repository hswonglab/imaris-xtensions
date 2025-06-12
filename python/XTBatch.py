 #  LinearUnmixing: An Imaris XTension to apply linear unmixing to an image
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Eric Gai.

'''
This script contains functions to enable batch operation of XTensions
'''

try:
    import traceback  
    import logging
    import ImarisLib
    import os
    from tqdm.contrib.itertools import product
    import numpy as np
    from tkinter import *
    from tkinter import messagebox
    from tkinter import filedialog
    from utils import GetImageSubSliceArray
    from matplotlib import pyplot as plt
except Exception as e:
    print(e)
    input("Press enter to exit;")
    raise

# def Main(aImarisId):

#     # Create an ImarisLib object
#     vImarisLib = ImarisLib.ImarisLib()

#     # Get an imaris object with id aImarisId
#     vImarisApplication = vImarisLib.GetApplication(aImarisId)

#     # Check if the object is valid
#     if vImarisApplication is None:
#         messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
#         return
    
#     print(f'Connected to Imaris application (id={aImarisId})')
    
#     curr_image_path = vImarisApplication.GetCurrentFileName()
#     # extract directory for current image
#     image_folder_path='\\'.join(curr_image_path.split('\\')[:-1])
#     # make list of all .ims files in current directory
#     all_image_paths=[f for f in os.listdir(image_folder_path) if f.endswith('.ims')]
#     for image_path in all_image_paths:
#         # logpath = image_path + '.log'
#         # logging.basicConfig(format=LOG_FORMAT, filename=logpath, level=logging.INFO)
#         image_path=image_folder_path+'\\'+image_path
#         vImarisApplication.FileOpen(image_path,'')
#         logging.info('----- Begin Editing %s -----', image_path)
#             # Get the image and channels
#         vNumberOfImages = vImarisApplication.GetNumberOfImages()
#         if vNumberOfImages != 1:
#             messagebox.showwarning('Only 1 image may be open at a time for this XTension')
#             return
#         vImage = vImarisApplication.GetImage(0)

#         vImageNew = configure_channels(vImage,vNewChannelNames,vNewChannelColors,confirmed=True)

#         vImarisApplication.SetImage(0, vImageNew)

#         path_strings=image_path.split('.')
#         path_strings[-2]+='XTBatch'
#         new_image_path='.'.join(path_strings)
#         logging.info('Saving changes to %s', new_image_path)
#         vImarisApplication.FileSave(new_image_path,'')
#         logging.info('----- Done Editing %s -----', image_path)

    
    # path_strings=image_path.split('.')
    # path_strings[-2]+='XT'


# def XTBatch(aImarisId):
#     # Initialize and launch Tk window, then hide it.
#     vRootTkWindow = Tk()
#     vRootTkWindow.withdraw()

#     try:
#         Main(aImarisId)
#     except Exception as exception:
#         print(traceback.print_exception(type(exception), exception, exception.__traceback__))
#     messagebox.showinfo('Complete', 'The XTension has terminated.')

def XTBatch(vImarisApplication,fn,args):
    ''' Applies an operation to all .ims files in the directory of the currently opened image. 
    
    Parameters
    ----------
    vImarisApplication : IApplication
        Imaris application object currently connected
    fn : Callable[ [IDataset, *args], IDataset ]
        function to apply to images in each file
    args : tuple(...) 
        tuple of variables to be passed to fn as arguments
    '''
    overwrite=messagebox.askyesno(
        'Save Options.',
        'Would you like to overwrite the existing existing images with modified images? \n Otherwise modified images will be saved as a separate files ending in "XTBatch.ims"'
        '\n Warning: please select "No". The "Yes" option is not fully functional at this time.'
    )
    curr_image_path = vImarisApplication.GetCurrentFileName()
    # extract directory for current image
    image_folder_path='\\'.join(curr_image_path.split('\\')[:-1])
    # make list of all .ims files in current directory
    all_image_paths=[f for f in os.listdir(image_folder_path) if f.endswith('.ims')]

    # import pdb
    # pdb.set_trace() 

    # vImarisApplication.FileSave(curr_image_path,'')

    for image_path in all_image_paths:
        image_path=image_folder_path+'\\'+image_path
        vImarisApplication.FileOpen(image_path,'')
        logging.info('----- Begin Editing %s -----', image_path)
            # Get the image and channels
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return
        vImage = vImarisApplication.GetImage(0)

        vImageNew = fn(vImage,*args)

        vImarisApplication.SetImage(0, vImageNew)

        if overwrite:
            new_image_path=image_path
        else:
            path_strings=image_path.split('.')
            path_strings[-2]+='XTBatch'
            new_image_path='.'.join(path_strings)
        logging.info('Saving changes to %s', new_image_path)
        vImarisApplication.FileSave(new_image_path,'')
        logging.info('----- Done Editing %s -----', image_path)