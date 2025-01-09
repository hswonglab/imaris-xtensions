#  ImportStatistics: Import new statistics for Imaris objects
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Christopher Skalnik and Eric Gai.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Import Statistics" icon="Python3" tooltip="Import new statistics for Imaris objects.">
#         <Command>Python3XT::ImportStatistics(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ImportStatistics imports custom statistics for a surface object from a CSV file.

The CSV should have a column for IDs of the surface objects, and a column for each 
custom statistic to be imported. The first row of the CSV should be a header row 
with the names of the statistics. 

An error will be thrown if the first row of the CSV (the header) does not have
exactly these columns, in this order.

This XTension supports batch operations. The user will be prompted to choose 
whether all .ims files in the directory of the current image shall be modified. 

Whenever this XTension operates on a file, it tracks all changes in a log file.
If the file currently opened is at path `path`, then the log file is at
`path.txt`. When called in batch mode, all logs will be written in `path.txt` 
corresponding to the file from which the XTension was called. 

This XTension will only save changes when run in batch mode. Otherwise, 
logged changes may not actually be saved if the user chooses not to.
'''

# essential dependencies
try:
    import csv
    import logging
    import traceback
    import ImarisLib
    # from XTBatch import XTBatch
    import tkinter as tk
    import pandas as pd
    import numpy as np
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
        tk.messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return
    
    print(f'Connected to Imaris application (id={aImarisId})')

    image_path = vImarisApplication.GetCurrentFileName()
    logpath = image_path + '.log'
    
    logging.basicConfig(format=LOG_FORMAT, filename=logpath, level=logging.INFO)
    logging.info('----- Begin Editing %s -----', image_path)

    # batch functionalities are not yet compatible with this XTension
    # batched=tk.messagebox.askyesno(
    #     'Batched Operation.',
    #     'Would you like to apply changes to all .ims files in this folder?'
    # )

    batched=False

    if batched:
        pass
    else:
        # Get the image and channels
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            tk.messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return

        # Get the factory
        vFactory = vImarisApplication.GetFactory()
        # Get the current scene
        vScene = vImarisApplication.GetSurpassScene()
        vNumberSurpassItems=vScene.GetNumberOfChildren()
        # get all the items in the current scene
        NameObjects=[]
        for vChildIndex in range(0,vNumberSurpassItems):
            NameObjects.append(vScene.GetChild(vChildIndex).GetName())

        # make a tkinter object, ask user to select Imaris object to add statistics to, record selection, and close window once selected
        root = tk.Tk()
        name_list = tk.StringVar(root,value=tuple(NameObjects))
        question_label = tk.Label(root, text="Select the surface object to which the statistic will be added")
        question_label.pack()
        l=tk.Listbox(root,listvariable=name_list,selectmode=tk.SINGLE)
        l.config(width=0)
        l.pack()
        def action():
            if l.curselection():
                if vImarisApplication.GetFactory().IsSurfaces(vScene.GetChild(l.curselection()[0])):
                    root.quit()
                else:
                    print('Please select a surfaces object')
    
        button = tk.Button(root, text="select",command=action)
        button.pack()
        root.mainloop()
        vObjectIndex=l.curselection()[0]
        root.destroy()
        logging.info(f'User selected {NameObjects[vObjectIndex]} to add statistics')

        # vImarisApplication.SetImage(0, vImageNew)
        # logging.info('Asking user to save image.')
        # saved = tk.messagebox.askyesno(
        #     'Save changes.',
        #     'Please save or discard changes. Did you save the file?'
        # )
        # logging.info('User reports that they saved changes: %s', saved)

        with tk.filedialog.askopenfile(mode='r', title='Select statistic CSV file to be imported') as f:
            logging.info(f'Reading statistics from {f.name}')
            new_stats_df=pd.read_csv(f)

        # check formatting of statistics dataframe

        if new_stats_df.iloc[:,0].name=='OriginalID':
            id='OriginalID'
        elif new_stats_df.iloc[:,0].name=='ID':
            id='ID'
        else:
            raise(RuntimeError('The first column of the CSV must be "ID" or "Original ID"'))
        
        # get the selected surface objects
        vObjects=vScene.GetChild(vObjectIndex)
        vSurfaces=vFactory.ToSurfaces(vObjects)

        # set up arguments for adding statistics
        vIndividualSurfaceIDs=new_stats_df[id]
        vIndividualStatUnits=[None]*len(vIndividualSurfaceIDs)
        #Create Tuple list for each surface in time
        vSurfaceStatFactors=(['Surface']*len(vIndividualSurfaceIDs),
                    [str(1)]*len(vIndividualSurfaceIDs))
        vSurfaceStatFactorName=['Category','Time']
        stat_name_list=vSurfaces.GetStatisticsNames()

        # vAllTimeIndices = []
        # for vNextSurface in range (vNumberOfSurfaces):
        #     vAllTimeIndices.append(vSurfaces.GetTimeIndex(vNextSurface))
        # print(vAllTimeIndices,len(vAllTimeIndices))
        ##############################################################################
        for i in range(1,len(new_stats_df.columns)):
            # get name of statistic
            new_stat_name=new_stats_df.iloc[:,i].name
            if new_stat_name in stat_name_list:
                proceed = tk.messagebox.askyesno(
                    'Save changes.',
                    f'{NameObjects[vObjectIndex]} already contains statistic {new_stat_name} \n Would you like to overwrite the existing values?'
                )
                logging.info(f'Found existing statistic {new_stat_name}. User chose to overwrite: {proceed}.')
            else:
                proceed=True
            if proceed:
                vSurfaceStatNames=[new_stat_name]*len(vIndividualSurfaceIDs)
                # get value of statistics
                vSurfaceStatValues=list(new_stats_df.iloc[:,i])
                # add statistic to surface
                vSurfaces.AddStatistics(vSurfaceStatNames, vSurfaceStatValues,
                                        vIndividualStatUnits, vSurfaceStatFactors,
                                        vSurfaceStatFactorName, vIndividualSurfaceIDs)
                logging.info(f'Added new statistic {new_stat_name}.')
        logging.info('----- Done Editing %s -----', image_path)

    print('Changes complete.')

def ImportStatistics(aImarisId):
    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = Tk()
    vRootTkWindow.withdraw()

    try:
        Main(aImarisId)
    except Exception as exception:
        print(traceback.print_exception(type(exception), exception, exception.__traceback__))
    tk.messagebox.showinfo('Complete', 'The XTension has terminated.')
