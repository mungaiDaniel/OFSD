import functools
import logging
from flask_jwt_extended import verify_jwt_in_request, get_jwt
import app.utils.responses as error
from flask import request

def permission(arg):
    def check_permissions(f):
        
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            
            auth = request.authorization
            
            if auth is None and 'Authorization' in request.headers:
                try:
                    
                    verify_jwt_in_request()
                    claims = get_jwt()
                    
                    if claims['admin'] < arg:
                        
                        return error.NOT_ADMIN
                except ValueError:
                    
                    return error.HEADER_NOT_FOUND
                
                except Exception as why:
                    logging.error(why)
                    
                    return error.INVALID_INPUT_422
            
            return f(*args, **kwargs)
        
        return decorated
    
    return check_permissions

def super_admin_required(f):
    """
    Restrict a route to super_admin. Every delete and every edit in the system
    goes through this; normal workflow (advancing batch stages, approving
    withdrawals, confirming emails) does not. Place it BELOW @jwt_required().
    Role is read from the database (not the JWT claim), so a demoted user loses
    access immediately.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # Imported lazily: edit_service imports models that import route modules.
        from app.Funds.edit_service import require_role
        _, error_response = require_role(roles=("super_admin",))
        if error_response:
            return error_response
        return f(*args, **kwargs)

    return decorated
