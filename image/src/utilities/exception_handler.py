"""
Wrapper/decorator for inner functions.

"""
import sys
import traceback
from utilities.logging import debug, error

def exception_handler(function):
    def inner_function(*args, **kwargs):
        try:
            function(*args, **kwargs)
        except Exception as exception:
            error(f"During execution the following error occured: {str(exception.__doc__)} Arguments: {exception.args}")
            error(str(exception))
            debug(traceback.format_exc())
            sys.exit(1)
    return inner_function
