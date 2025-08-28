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
    import logging
    import os
    import traceback

    import ImarisLib
    import numpy as np
    from tkinter import *
    from tkinter import messagebox
    from tkinter import filedialog
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

def XTBatch(vImarisApplication,fn,args=None,im_args_dict=None,operate_on_image=True):
    ''' Applies an operation to all .ims files in the directory of the currently opened image. 
    
    Parameters
    ----------
    vImarisApplication : IApplication
        Imaris application object currently connected
    fn : Callable[ [IDataset, *args], IDataset ] or Callable[ [IApplication, *args], None ]
        function to apply to each file
        see documentation for operate_on_images for more information on input and output types
    args : tuple(...) (optional)
        tuple of variables to be passed to fn as arguments
    im_args_dict : dict[str:tuple(...)] (optional)
        use this argument if any arguments of fn are specific to each image
        dictionary with image names as keys and image-specific arguments as values  
        the keys must match the full file names of the .ims files (without the extension) to be applied correctly
        the values must be packed in a tuple since it will be unpacked before being passed to fn
    operate_on_image : bool 
        if True, fn should operate directly on the image (IDataset object) 
            XTBatch will expect a new image to be returned by each call to fn, replace the existing image with it, then save the file with the new image
        if False, fn will have direct access to the IApplication object, which can operate on both the image and the associated surpass objects  
            XTBatch will expect fn to interact directly with the IApplication object, and save the state of the file after fn is applied 
    '''
    args = args or []
    # overwrite=messagebox.askyesno(
    #     'Save Options.',
    #     'Would you like to overwrite the existing existing images with modified images? \n Otherwise modified images will be saved as a separate files ending in "XTBatch.ims"'
    #     '\n Warning: please select "No". The "Yes" option is not fully functional at this time.'
    # )
    overwrite=False #Imaris does not handle the opened file correctly for overwriting in this implementation

    curr_image_path = vImarisApplication.GetCurrentFileName()
    # extract directory for current image
    image_folder_path='\\'.join(curr_image_path.split('\\')[:-1])
    # make list of all .ims files in current directory
    all_image_paths=[f for f in os.listdir(image_folder_path) if f.endswith('.ims')]

    # import pdb
    # pdb.set_trace() 

    # vImarisApplication.FileSave(curr_image_path,'')

    for image_path in all_image_paths:
        if im_args_dict is not None:
            try:
                im_args=im_args_dict[image_path[:-4]]
            except KeyError:
                logging.warning(f'Attempted to find image-specific argument for {image_path} but none was found.')
                logging.info(f'Skipping image {image_path}')
                continue
        else:
            im_args = []
        image_path=image_folder_path+'\\'+image_path
        vImarisApplication.FileOpen(image_path,'')
        logging.info('----- Begin Editing %s -----', image_path)
            # Get the image and channels
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return
        if operate_on_image:
            vImage = vImarisApplication.GetImage(0)

            vImageNew = fn(vImage,*args,*im_args)

            vImarisApplication.SetImage(0, vImageNew)
        else:
            fn(vImarisApplication,*args,*im_args)

        if overwrite:
            new_image_path=image_path
        else:
            path_strings=image_path.split('.')
            path_strings[-2]+='XTBatch'
            new_image_path='.'.join(path_strings)
        logging.info('Saving changes to %s', new_image_path)
        vImarisApplication.FileSave(new_image_path,'')
        logging.info('----- Done Editing %s -----', image_path)
