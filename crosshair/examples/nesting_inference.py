from typing import *


def mydiv(x: int, y: int) -> Optional[float]:
    '''
    pre: y != 0
    post: isinstance(return, float)
    '''
    return None if y == 0 else x / y

def myavg(t: Tuple[int, ...]) -> Optional[float]:
    '''
    pre: len(t) > 0
    post: isinstance(return, float)
    '''
    return mydiv(sum(t), len(t))