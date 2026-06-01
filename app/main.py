from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from .database import engine, Base, SessionLocal
from .models import Customer
from .call_engine import start_call
from .models import Feedback
import threading
from .sentiment import analyze_sentiment
from fastapi.staticfiles import StaticFiles

app = FastAPI()
templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = SessionLocal()
    customers = db.query(Customer).all()
    return templates.TemplateResponse("index.html", {"request": request, "customers": customers})

@app.post("/add_customer")
def add_customer(name: str = Form(...), phone: str = Form(...)):
    db = SessionLocal()
    new_customer = Customer(name=name, phone=phone)
    db.add(new_customer)
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.get("/start_call/{customer_id}")
def trigger_call(customer_id: int):
    thread = threading.Thread(
        target=process_call,
        args=(customer_id,)
    )
    thread.start()

    return RedirectResponse("/", status_code=303)

def process_call(customer_id: int):
    db = SessionLocal()

    feedback_data = start_call()

    sentiment = analyze_sentiment(feedback_data["suggestion"])

    new_feedback = Feedback(
    customer_id=customer_id,
    rating=feedback_data["rating"],
    recommendation=feedback_data["recommendation"],
    suggestion=feedback_data["suggestion"],
    sentiment=sentiment,
    recording_path=feedback_data["recording_path"]
)

    db.add(new_feedback)
    db.commit()
    db.close()

@app.get("/history", response_class=HTMLResponse)
def call_history(request: Request):
    db = SessionLocal()
    feedbacks = db.query(Feedback).all()
    return templates.TemplateResponse("history.html", {"request": request, "feedbacks": feedbacks})

app.mount("/recordings", StaticFiles(directory="recordings"), name="recordings")