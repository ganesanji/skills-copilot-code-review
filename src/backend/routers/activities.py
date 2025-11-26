"""
Endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from typing import Dict, Any, Optional, List

from ..database import activities_collection, teachers_collection, announcements_collection
from fastapi import Body
from datetime import datetime
# Announcement Endpoints
@router.get("/announcements", response_model=List[Dict[str, Any]])
def get_announcements():
    """Get all announcements (for management dialog)"""
    return [
        {**a, "_id": str(a.get("_id", ""))} for a in announcements_collection.find({})
    ]

@router.get("/active-announcements", response_model=List[Dict[str, Any]])
def get_active_announcements():
    """Get currently active announcements (for banner)"""
    now = datetime.now().isoformat()
    query = {"expiration_date": {"$gte": now}}
    return [
        {**a, "_id": str(a.get("_id", ""))}
        for a in announcements_collection.find(query)
        if (not a.get("start_date") or a["start_date"] <= now)
    ]

@router.post("/announcements", response_model=Dict[str, Any])
def add_announcement(
    message: str = Body(...),
    expiration_date: str = Body(...),
    start_date: str = Body(None),
    created_by: str = Body(...)
):
    """Add a new announcement (signed-in users only)"""
    if not created_by:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not expiration_date:
        raise HTTPException(status_code=400, detail="Expiration date required")
    ann = {
        "message": message,
        "expiration_date": expiration_date,
        "start_date": start_date,
        "created_by": created_by,
        "created_at": datetime.now().isoformat()
    }
    result = announcements_collection.insert_one(ann)
    ann["_id"] = str(result.inserted_id)
    return ann

@router.put("/announcements/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: str = Body(...),
    expiration_date: str = Body(...),
    start_date: str = Body(None),
    updated_by: str = Body(...)
):
    """Update an announcement (signed-in users only)"""
    if not updated_by:
        raise HTTPException(status_code=401, detail="Authentication required")
    update = {
        "message": message,
        "expiration_date": expiration_date,
        "start_date": start_date,
        "updated_by": updated_by,
        "updated_at": datetime.now().isoformat()
    }
    result = announcements_collection.update_one({"_id": announcement_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    ann = announcements_collection.find_one({"_id": announcement_id})
    ann["_id"] = str(ann["_id"])
    return ann

@router.delete("/announcements/{announcement_id}")
def delete_announcement(announcement_id: str, deleted_by: str = Body(...)):
    """Delete an announcement (signed-in users only)"""
    if not deleted_by:
        raise HTTPException(status_code=401, detail="Authentication required")
    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted", "id": announcement_id}

router = APIRouter(
    prefix="/activities",
    tags=["activities"]
)


@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any])
def get_activities(
    day: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get all activities with their details, with optional filtering by day and time

    - day: Filter activities occurring on this day (e.g., 'Monday', 'Tuesday')
    - start_time: Filter activities starting at or after this time (24-hour format, e.g., '14:30')
    - end_time: Filter activities ending at or before this time (24-hour format, e.g., '17:00')
    """
    # Build the query based on provided filters
    query = {}

    if day:
        query["schedule_details.days"] = {"$in": [day]}

    if start_time:
        query["schedule_details.start_time"] = {"$gte": start_time}

    if end_time:
        query["schedule_details.end_time"] = {"$lte": end_time}

    # Query the database
    activities = {}
    for activity in activities_collection.find(query):
        name = activity.pop('_id')
        activities[name] = activity

    return activities


@router.get("/days", response_model=List[str])
def get_available_days() -> List[str]:
    """Get a list of all days that have activities scheduled"""
    # Aggregate to get unique days across all activities
    pipeline = [
        {"$unwind": "$schedule_details.days"},
        {"$group": {"_id": "$schedule_details.days"}},
        {"$sort": {"_id": 1}}  # Sort days alphabetically
    ]

    days = []
    for day_doc in activities_collection.aggregate(pipeline):
        days.append(day_doc["_id"])

    return days


@router.post("/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str, teacher_username: Optional[str] = Query(None)):
    """Sign up a student for an activity - requires teacher authentication"""
    # Check teacher authentication
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")

    # Get the activity
    activity = activities_collection.find_one({"_id": activity_name})
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Validate student is not already signed up
    if email in activity["participants"]:
        raise HTTPException(
            status_code=400, detail="Already signed up for this activity")

    # Add student to participants
    result = activities_collection.update_one(
        {"_id": activity_name},
        {"$push": {"participants": email}}
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, detail="Failed to update activity")

    return {"message": f"Signed up {email} for {activity_name}"}


@router.post("/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str, teacher_username: Optional[str] = Query(None)):
    """Remove a student from an activity - requires teacher authentication"""
    # Check teacher authentication
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")

    # Get the activity
    activity = activities_collection.find_one({"_id": activity_name})
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Validate student is signed up
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400, detail="Not registered for this activity")

    # Remove student from participants
    result = activities_collection.update_one(
        {"_id": activity_name},
        {"$pull": {"participants": email}}
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, detail="Failed to update activity")

    return {"message": f"Unregistered {email} from {activity_name}"}
