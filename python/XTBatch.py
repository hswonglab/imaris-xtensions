#  XTBatch: A wrapper that can be applied to Imaris XTensions to enable batching.
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Eric Gai and Christopher Skalnik.

'''
This script contains functions to enable batch operation of XTensions. To use,
import the XTBatch function into the script implementing your XTension. Then
call XTBatch with a function implementing your XTension as an argument.
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


def XTBatch(
    vImarisApplication, fn, args=None, im_args_dict=None,
    operate_on_image=True
):
    '''Applies an operation to all .ims files in the directory of the currently-open image.
    
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
        Arguments to `fn` that should override the default arguments in `args`
        for a particular image, expressed as a mapping from image path
        (excluding the `.ims` extension) to the arguments (as a tuple) that
        should be used instead of `args` for that image.
    operate_on_image : bool 
        If True, fn should operate directly on the image (IDataset object).
        XTBatch will expect a new image to be returned by each call to fn,
        replace the existing image with it, then save the file with the new
        image.
        If False, fn will have direct access to the IApplication object, which
        can operate on both the image and the associated surpass object.
        XTBatch will expect fn to interact directly with the IApplication
        object, and save the state of the file after fn is applied
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
