#  ChannelArithmeticsBoolean: An Imaris XTension to perform channel arithmetics faster than the matlab extension (hopefully)
#
#  Copyright © 2023 MASSACHUSETTS INSTITUTE OF TECHNOLOGY.
#  All rights reserved.
#
#  Written by Amy Huang.
#
#    <CustomTools>
#      <Menu>
#       <Item name="Channel Arithmetics Boolean" icon="Python3" tooltip="Performs channel arithmetics similar to the Matlab extension.">
#         <Command>Python3XT::ChannelArithmeticsBoolean(%i)</Command>
#       </Item>
#      </Menu>
#    </CustomTools>

'''ChannelArithmetics allows for the user to perform channel arithmetics. Hopefully this is faster than the matlab implementation

This XTension supports batch operations. The user will be prompted to choose
whether all .ims files in the directory of the current image shall be modified

Note (Amy, 2025-02-02): This function is in development; I've only tested it on addition so far and it seems to work but no guarentees use at your own risk!
Note (Nicole, 2025-05-09): Thanks for the function Amy! Just trying to make it work for boolean expressions (setting clip from 0 to 1 at the end)
Note (Amy, 2025-06-07): I've attempted to add and/or operations, also modified the clip for booleans
'''

#essential dependencies
try:
    import ImarisLib
    import numpy as np

    import tkinter as tk
    from tkinter import simpledialog
    from tkinter import messagebox

    from tqdm import tqdm
    from tqdm.contrib.itertools import product

    import re
    import ast
    import operator
except Exception as e:
    print(e)
    input("Press enter to exit;")
    raise

#nonessential dependences
try:
    from XTBatch import XTBatch
    batch_enabled=True
except Exception as e:
    print(e)
    batch_enabled=False
    input("Press enter to exit;")

def get_formula_from_user():
    formula_str = simpledialog.askstring("Input", "Enter channel arithmetic formula (e.g. ch1 + ch3 * ch10)")
    return formula_str

def ChannelArithmeticsBoolean(aImarisId):
    
    # Initialize and launch Tk window, then hide it.
    vRootTkWindow = tk.Tk()
    vRootTkWindow.withdraw()

    # Create an ImarisLib object
    vImarisLib = ImarisLib.ImarisLib()

    # Get an imaris object with id aImarisId
    vImarisApplication = vImarisLib.GetApplication(aImarisId)

    # Check if the object is valid
    if vImarisApplication is None:
        messagebox.showerror('Error', f'Failed to connect to Imaris application (id={aImarisId})')
        return
    print(f'Connected to Imaris application (id={aImarisId})')

    # Get Image
    vImage = vImarisApplication.GetImage(0)

    # Get prompt
    formula_str = get_formula_from_user()

    # Ask for batch
    if batch_enabled:
        batched=messagebox.askyesno(
            'Batched Operation.',
            'Would you like to apply changes to all .ims files in this folder?'
        )
    else:
        batched=False

    if batched: 
        try: 
            XTBatch(vImarisApplication, RunChannelArithmetics, (formula_str, True))
        except Exception as e: 
            print(e)
            input("Press enter to exit;")
    else: 
        vNumberOfImages = vImarisApplication.GetNumberOfImages()
        if vNumberOfImages != 1:
            messagebox.showwarning('Only 1 image may be open at a time for this XTension')
            return
        try: 
            vImageNew = RunChannelArithmetics(vImage, formula_str)
            vImarisApplication.SetImage(0, vImageNew)
        except Exception as e: 
            print(e)
            input("Press enter to exit;")

    messagebox.showinfo('Complete', 'The XTension has terminated.')


def RunChannelArithmetics(vImage, formula_str, verbose=True): 

    # Make a new image 
    vImageNew = vImage.Clone()

    # Get new channel index and name
    ch_out_index = vImage.GetSizeC()
    ch_out_name = formula_str
    if verbose: 
        print(f"Creating channel {ch_out_index + 1}, named {formula_str}")
    vImageNew.SetSizeC(ch_out_index + 1)
    vImageNew.SetChannelName(ch_out_index, ch_out_name)

    # Get channel names and indices, e.g. {"ch3": 2, "ch12": 11}
    channel_indices = {match: int(match[2:]) - 1 for match in re.findall(r'ch\d+', formula_str)}

    # Define allowed operators 
    allowed_operators = {
        ast.Add: operator.add, 
        ast.Sub: operator.sub, 
        ast.Mult: operator.mul, 
        ast.Lt: np.less, 
        ast.Gt: np.greater, 
        ast.LtE: np.less_equal, 
        ast.GtE: np.greater_equal, 
        ast.Eq: np.equal, 
        ast.NotEq: np.not_equal, 
        ast.And: np.logical_and, 
        ast.Or: np.logical_or
    }

    # Define a class which can parse arithmetic expressions
    class EvalVisitor(ast.NodeVisitor): 
        
        def visit_BinOp(self, node): 
            left = self.visit(node.left)
            right = self.visit(node.right)
            if type(node.op) in allowed_operators: 
                return allowed_operators[type(node.op)](left, right)
            else: 
                raise ValueError("Unsupported operator: {}".format(node.op))
        
        def visit_Name(self, node):
            if node.id.startswith("ch") and node.id in channel_values: 
                return np.array(channel_values[node.id])
            raise ValueError("Undefined variable: {}".format(node.id))
            
        def visit_Compare(self, node):
            left = self.visit(node.left)
            if len(node.ops) != 1 or len(node.comparators) != 1: 
                raise ValueError("Only simple comparisons are supported")
            right = self.visit(node.comparators[0])
            op_type = type(node.ops[0])
            if op_type in allowed_operators: 
                return np.where(allowed_operators[op_type](left, right), True, False) 
            else: 
                raise ValueError("Undefined variable: {}".format(node.id))
        
        def visit_BoolOp(self, node):
            if len(node.values) != 2: 
                raise ValueError("Can only perform BoolOp with two values")
            values0 = self.visit(node.values[0])
            values1 = self.visit(node.values[1])
            op_type = type(node.op)
            if op_type in allowed_operators: 
                return allowed_operators[type(node.op)](values0, values1)
            else: 
                raise ValueError("Undefined variable: {}".format(node.id))
        
        def visit_Num(self, node): 
            return np.array(node.n)

        def visit_Constant(self, node): 
            return np.array(node.value)
        
        def visit_Expr(self, node):
            return self.visit(node.value)

    # get channel values
    channel_values = {} # start by initializing an empty dictionary

    ### slice by slice operations originally developed by Eric in LinearUnmixing.py; modified for these purposes here
    #process data slice by slice in square windows of length vWindowSize pixels
    vWindowSize = 10000 # larger windows can speed up execution but will be more memory-intensive
    vNumSlices = vImage.GetSizeZ()
    vXSize = vImage.GetSizeX()
    vYSize=vImage.GetSizeY()

    is_first = True
    for x,y,z in product(range(0,vXSize,vWindowSize),range(0,vYSize,vWindowSize),range(vNumSlices)):
        window_x_len=min(vWindowSize,vXSize-x)
        window_y_len=min(vWindowSize,vYSize-y)

        for ch_name in channel_indices:
            channel_values[ch_name] = np.zeros((window_x_len,window_y_len))
            ch_index = channel_indices[ch_name]
            channel_values[ch_name] = np.array([np.frombuffer(row,dtype=np.uint8) for row in vImage.GetDataSubSliceBytes(aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=ch_index,aIndexT=0,aSizeX=window_x_len,aSizeY=window_y_len)])

        # parse arithmetic expression
        tree = ast.parse(formula_str, mode='eval')
        if is_first and verbose: 
            print("\n")
            print(ast.dump(ast.parse(formula_str)))
            print("\n")
            is_first = False

        # calculate
        new_channel_values = EvalVisitor().visit(tree.body)

        # bound values to 0, 255
        new_channel_values[new_channel_values>255] = 255; new_channel_values[new_channel_values<0] = 0
        new_channel_values_clipped = np.array(new_channel_values, dtype='uint8')
        
        # Add data to new channel in new Image
        vImageNew.SetDataSubSliceBytes(aData=[row.tobytes() for row in new_channel_values],aIndexX=x,aIndexY=y,aIndexZ=z,aIndexC=ch_out_index,aIndexT=0)

    return vImageNew
