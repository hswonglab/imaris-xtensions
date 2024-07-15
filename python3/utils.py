import numpy as np
import ImarisLib

def GetImageSubSliceArray(vImage,aIndexX,aIndexY,aIndexZ,aIndexC,aIndexT,aSizeX,aSizeY):
    return np.array([np.frombuffer(row,dtype=np.uint8) for row in vImage.GetDataSubSliceBytes(aIndexX,aIndexY,aIndexZ,aIndexC,aIndexT,aSizeX,aSizeY)])