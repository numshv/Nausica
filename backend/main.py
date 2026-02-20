from fastapi import FastAPI
from database import supabase

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Lucera API"}

@app.get("/test-db")
def test_db():
    response = supabase.table("brands").select("*").limit(1).execute()
    return {"connected": True, "data": response.data}