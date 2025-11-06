# Wong Lab Imaris XTensions

## Installation

To use these XTensions, follow these instructions:

1. Clone or download this repository to your local machine. You can place it
   wherever you like.
2. Open Imaris.
3. Open the Imaris preferences at "File > Preferences".
4. Under "Custom Tools" make sure the MATLAB runtimes are present (use the links
   in Imaris to download any missing runtimes that the XTensions you want to use
   require) and that you have specified a path to a Python 3.7 executable. If
   you need to install Python 3.7, you can do so using Anaconda.
5. Under the locations for Imaris to look for XTensions, add the "python" and/or
   "matlab" folders of this repository depending on which XTensions you want.
6. Restart Imaris.
7. The XTensions in this repository should appear in the "Image Processing" menu
   once you open an image. Click on an XTension's name to run it.

## How XTensions are Listed in Imaris

In each XTension file, you will see a comment with XML content like this (for
Python):

```xml
<CustomTools>
  <Menu>
   <Item name="XTension Name" icon="Python3" tooltip="XTension description.">
     <Command>Python3XT::XTensionName(%i)</Command>
   </Item>
  </Menu>
</CustomTools>
```

Imaris would display an entry under "Image Processing" for an extension called
`XTension Name`, and hovering over it would bring up a tooltip with `XTension
description.`. When you click on that entry, Imaris will look for a function
named `XTensionName` in a file called `XTension.py` and execute that function.

## Surface Representation

Sometimes, we want to transport cell segmentation data between software tools.
For example, we might want to segment cells using Cellpose and then use
[ImportSurfaces.py](python/ImportSurfaces.py) to load the segmented cell
surfaces into Imaris. Conversely, we might segment cells in Imaris and then use
[ExportSurfaces.py](python/ExportSurfaces.py) to export the surfaces for custom
analysis code. To make cell surfaces portable between software tools, we define
a simple representation for image segmentation data. This representation is
lightly adapted from how [Imaris](https://imaris.oxinst.com) provides surface
data through its XTension interface.

This representation has the following useful properties:

* It is both human- and machine-readable, so users can manually inspect the
  surface representation when debugging.
* Our format supports surfaces with boundaries defined with sub-voxel precision
  while making voxel-precision approximations easy.
* The representation is sparse, keeping exports space-efficient.
* We build on top of JSON, which is mature and widely supported. This means
  that if you want to write your own code to work with segmentation data,
  libraries to read and write JSON probably already exist for your language of 
  choice.
* Simple. We've tried to represent surfaces as simply as possible so that it's
  easy for users to use them in custom analysis scripts.

### Specification

Version: 0.1

Conceptually, we first define a rectangular prism that fully encloses the
surface. Then, we store a 3-dimensional mask that fills this enclosing box.
The mask stores positive values inside the surface and negative values outside
the surface. The precise boundary of the surface is the zero point interpolated
between the positive and negative values on either side of the boundary.

Segmentation data is represented as a JSON-formatted list of objects. Each
object has the following keys:

* `xRange`: Minimum and maximum x coordinates of the enclosing box.
* `yRange`: Minimum and maximum y coordinates of the enclosing box.
* `zRange`: Minimum and maximum z coordinates of the enclosing box.
* `mask`: The 3-dimensional mask, represented as triply-nested lists. The
  indices of these lists are the z, y, and x coordinates of each voxel in the
  mask, in that order. In other words, the value for the voxel at coordinates
  `(x, y, z)` is at `mask[z][y][x]`. Each voxel's coordinates are the
  coordinates of the *center* of the voxel, and voxels on all edges of the
  enclosing box are included.

For example, a cube with sides of length 2 centered at `(5, 6, 7)` can be
represented as follows:

```json
{
    "xRange": [3, 7],
    "yRange": [4, 8],
    "zRange": [5, 9],
    "mask": [
        [
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
        ],
        [
            [-1, -1, -1, -1, -1],
            [-1,  0,  0,  0, -1],
            [-1,  0,  0,  0, -1],
            [-1,  0,  0,  0, -1],
            [-1, -1, -1, -1, -1],
        ],
        [
            [-1, -1, -1, -1, -1],
            [-1,  0,  0,  0, -1],
            [-1,  0,  1,  0, -1],
            [-1,  0,  0,  0, -1],
            [-1, -1, -1, -1, -1],
        ],
        [
            [-1, -1, -1, -1, -1],
            [-1,  0,  0,  0, -1],
            [-1,  0,  0,  0, -1],
            [-1,  0,  0,  0, -1],
            [-1, -1, -1, -1, -1],
        ],
        [
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
            [-1, -1, -1, -1, -1],
        ],
    ]
}
```

Above we have used a "pretty" representation of the JSON object for
readability, but this is not required. To save space, you can use a more
compact representation without line breaks or indentation. Any good JSON parser
should be able to handle either representation, and our format is agnostic to
how the JSON-encoded data is stored.

### Usage

The following Python code loads a surface from a JSON file using our
representation:

```python
import json
import numpy as np

with open('surfaces.json', 'r') as f:
    surfaces_json = json.load(f)
xRange = surfaces_json[0]['xRange']
yRange = surfaces_json[0]['yRange']
zRange = surfaces_json[0]['zRange']
# The transpose leaves `mask` with axes (x, y, z).
mask = np.array(surfaces_json[0]['mask']).transpose([2, 1, 0])
```

### Notes

* Surface representations are not unique. For example, you can always expand
  the enclosing box and pad the extra space with negative values without
  changing the represented surface.
* Beware fencepost errors, as voxel coordinate assignment is somewhat atypical
  to match how Imaris represents surfaces. For `xRange = [3, 9]` and a mask
  with voxels of length 1, the mask will have 7 voxels, not 6, because voxels
  are included at both `x = 3` and at `x = 9`.

## Acknowledgements

Copyright © 2023-2024 Massachusetts Institute of Technology and Massachusetts
General Hospital. All rights reserved.

These XTensions were created in the [Wong Lab](https://hswonglab-ri.mit.edu/),
an [MIT](https://mit.edu) lab at the
[Ragon Institute](https://ragoninstitute.org/) of Mass General, MIT, and Harvard.

This work was supported by a variety of funding sources, including:

* The National Institute of General Medical Sciences of the National Institutes
  of Health under award number T32GM87237-14. The content is solely the
  responsibility of the authors and does not necessarily represent the official
  views of the National Institutes of Health.
