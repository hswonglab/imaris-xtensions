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
