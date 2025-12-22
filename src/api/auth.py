from fastapi import Header, HTTPException, Depends
from src.infrastructure.supabase_client import supabase

async def get_current_user(authorization: str = Header(...)):
    """
    Validates the Supabase JWT token and returns the user object.
    Expected format: Bearer <token>
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.split(" ")[1]
    print(f"DEBUG: Validating token starting with: {token[:20]}...")
    
    try:
        # Verify the token with Supabase
        # Note: res is a UserResponse object in recent versions
        res = supabase.auth.get_user(token)
        if not res.user:
            print("Auth error: No user returned from Supabase")
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return res.user
    except Exception as e:
        print(f"Auth error exception: {type(e).__name__}: {str(e)}")
        # Log more info if it's a supabase-py specific error
        if hasattr(e, 'message'):
            print(f"Supabase error message: {e.message}")
        raise HTTPException(status_code=401, detail=f"Unauthenticated: {str(e)}")
