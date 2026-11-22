from fastapi import APIRouter, Request, Body
from app.engine import evaluate
from app.web import render
router=APIRouter()
@router.get('/grouping')
def page(request:Request):
    return render(request,'grouping')
@router.post('/api/grouping')
def calculate(payload:dict=Body(default={})):
    return evaluate(payload,until=3)
