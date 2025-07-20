"""Store endpoints for Agent Protocol"""
from typing import List
from fastapi import APIRouter, HTTPException, Query, Depends

from ..models import StorePutRequest, StoreGetResponse, StoreSearchRequest, StoreSearchResponse, StoreItem, User
from ..core.auth_deps import get_current_user

router = APIRouter()


@router.put("/store/items")
async def put_store_item(request: StorePutRequest, user: User = Depends(get_current_user)):
    """Store an item in the LangGraph store"""
    
    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, request.namespace)
    
    # Get LangGraph store from database manager
    from ..core.database import db_manager
    store = db_manager.get_store()
    
    await store.aput(
        namespace=tuple(scoped_namespace),
        key=request.key,
        value=request.value
    )
    
    return {"status": "stored"}


@router.get("/store/items", response_model=StoreGetResponse)
async def get_store_item(
    key: str,
    namespace: List[str] = Query([]),
    user: User = Depends(get_current_user)
):
    """Get an item from the LangGraph store"""
    
    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, namespace)
    
    # Get LangGraph store from database manager
    from ..core.database import db_manager
    store = db_manager.get_store()
    
    item = await store.aget(tuple(scoped_namespace), key)
    
    if not item:
        raise HTTPException(404, "Item not found")
    
    return StoreGetResponse(
        key=key,
        value=item.value,
        namespace=list(scoped_namespace)
    )


@router.delete("/store/items")
async def delete_store_item(
    key: str,
    namespace: List[str] = Query([]),
    user: User = Depends(get_current_user)
):
    """Delete an item from the LangGraph store"""
    
    # Apply user namespace scoping
    scoped_namespace = apply_user_namespace_scoping(user.identity, namespace)
    
    # Get LangGraph store from database manager
    from ..core.database import db_manager
    store = db_manager.get_store()
    
    await store.adelete(tuple(scoped_namespace), key)
    
    return {"status": "deleted"}


@router.post("/store/search", response_model=StoreSearchResponse)
async def search_store_items(request: StoreSearchRequest, user: User = Depends(get_current_user)):
    """Search items in the LangGraph store"""
    
    # Apply user namespace scoping
    scoped_prefix = apply_user_namespace_scoping(user.identity, request.namespace_prefix)
    
    # Get LangGraph store from database manager
    from ..core.database import db_manager
    store = db_manager.get_store()
    
    # Search with LangGraph store
    results = await store.asearch(
        namespace_prefix=tuple(scoped_prefix),
        query=request.query,
        limit=request.limit or 20,
        offset=request.offset or 0
    )
    
    items = [
        StoreItem(
            key=r.key,
            value=r.value,
            namespace=list(r.namespace)
        )
        for r in results
    ]
    
    return StoreSearchResponse(
        items=items,
        total=len(items),  # LangGraph store doesn't provide total count
        limit=request.limit or 20,
        offset=request.offset or 0
    )


def apply_user_namespace_scoping(user_id: str, namespace: List[str]) -> List[str]:
    """Apply user-based namespace scoping for data isolation"""
    
    if not namespace:
        # Default to user's private namespace
        return ["users", user_id]
    
    # Allow explicit user namespaces
    if namespace[0] == "users" and len(namespace) >= 2 and namespace[1] == user_id:
        return namespace
    
    # For development, allow all namespaces (remove this for production)
    return namespace