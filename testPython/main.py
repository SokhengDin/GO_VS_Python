import os
import uuid
import logging
import time
import psutil
import json

from enum import Enum
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Dict
from prometheus_fastapi_instrumentator import Instrumentator

from sqlalchemy.orm import Session, sessionmaker, mapped_column, Mapped, relationship, declarative_base

from sqlalchemy import engine, create_engine, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

load_dotenv()

logging.basicConfig(
    level       = logging.INFO
    , format    ='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    , handlers  = [
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

Base    = declarative_base()

DB_HOST=os.getenv("DB_HOST", "bench_db")
DB_PORT=os.getenv("DB_PORT", "5432")
DB_USER=os.getenv("DB_USER", "postgres")
DB_PASS=os.getenv("DB_PASS", "CDC123")
DB_NAME=os.getenv("DB_NAME", "test")
DB_DIALECT=os.getenv("DB_DIALECT", "postgresql")

engine = create_engine(
    f'{DB_DIALECT}://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}',
    pool_size       = 10,
    max_overflow    = 5,
    pool_timeout    = 10,
    pool_recycle    = 1800,
    echo            = False
)

SessionLocal = sessionmaker(
    bind        = engine
    , autoflush = False
)

def getSession():
    try:
        session = SessionLocal()
        yield session
    finally:
        session.close()

class PetTypeEnum(str, Enum):
    DOG         = "dog"
    CAT         = "cat"
    BIRD        = "bird"

class User(Base):
    __tablename__ = "users"

    id          : Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        : Mapped[str]           = mapped_column(String)
    
    first_name  : Mapped[str]           = mapped_column(String)
    last_name   : Mapped[str]           = mapped_column(String)

    is_active   : Mapped[bool]          = mapped_column(Boolean, default=True)

    pets        = relationship('Pet', back_populates='user')

class Pet(Base):
    __tablename__ = "pets"

    id          : Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     : Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'))

    name        : Mapped[str]           = mapped_column(String)
    type        : Mapped[str]           = mapped_column(String)

    is_active   : Mapped[bool]          = mapped_column(Boolean, default=True)

    user        = relationship('User', back_populates='pets')


class USER_SCHEMA_IN(BaseModel):
    name            : str
    first_name      : str
    last_name       : str
    is_active       : bool = True

    class Config:
        from_attributes = True

class PET_SCHEMA_IN(BaseModel):
    name            : str
    type            : PetTypeEnum
    is_active       : bool = True

    class Config:
        from_attributes = True

class PET_SCHEMA_OUT(BaseModel):
    id              : uuid.UUID
    name            : str
    type            : str
    is_active       : bool

    class Config:
        from_attributes = True

class USER_SCHEMA_OUT(BaseModel):
    id              : uuid.UUID
    name            : str
    first_name      : str
    last_name       : str
    is_active       : bool
    pets            : List[PET_SCHEMA_OUT] = []

    class Config:
        from_attributes = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Starting application ...")
    yield
    logger.info("Shutdown application")


app = FastAPI(
    lifespan    = lifespan
    , title     = "FastAPI API Benchmark"
)

# Setup Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Store metrics history
metrics_history = {
    "timestamps": [],
    "cpu": [],
    "memory": [],
    "requests": 0,
    "request_count_history": [],
    "last_request_time": time.time(),
    "requests_per_sec": 0.0,
    "response_times": [],
}

# Add dashboard route
@app.get("/dashboard/", response_class=HTMLResponse)
async def get_dashboard():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>FastAPI Metrics Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .metrics-container { display: flex; flex-wrap: wrap; gap: 20px; }
            .metric-card { background: #f5f5f5; border-radius: 8px; padding: 15px; flex: 1; min-width: 300px; }
            h1, h2 { color: #333; }
            .chart-container { height: 300px; margin-top: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>FastAPI Performance Dashboard</h1>
            
            <div class="metrics-container">
                <div class="metric-card">
                    <h2>System Metrics</h2>
                    <p>CPU Usage: <span id="cpu-usage">-</span>%</p>
                    <p>Memory Usage: <span id="memory-usage">-</span> MB</p>
                    <p>Requests Processed: <span id="requests-processed">-</span></p>
                    <p>Requests Per Second: <span id="requests-per-sec">-</span></p>
                    <p>Avg Response Time: <span id="avg-response-time">-</span> ms</p>
                    <div class="chart-container">
                        <canvas id="system-chart"></canvas>
                    </div>
                </div>
                
                <div class="metric-card">
                    <h2>Response Time</h2>
                    <div class="chart-container">
                        <canvas id="response-chart"></canvas>
                    </div>
                </div>
                
                <div class="metric-card">
                    <h2>Requests Per Second</h2>
                    <div class="chart-container">
                        <canvas id="rps-chart"></canvas>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // Initialize charts
            const systemCtx = document.getElementById('system-chart').getContext('2d');
            const systemChart = new Chart(systemCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'CPU Usage (%)',
                            data: [],
                            borderColor: 'rgba(54, 162, 235, 1)',
                            tension: 0.1,
                            fill: false
                        },
                        {
                            label: 'Memory (MB)',
                            data: [],
                            borderColor: 'rgba(255, 99, 132, 1)',
                            tension: 0.1,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
            
            const responseCtx = document.getElementById('response-chart').getContext('2d');
            const responseChart = new Chart(responseCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Response Time (ms)',
                            data: [],
                            borderColor: 'rgba(75, 192, 192, 1)',
                            tension: 0.1,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
            
            const rpsCtx = document.getElementById('rps-chart').getContext('2d');
            const rpsChart = new Chart(rpsCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Requests Per Second',
                            data: [],
                            borderColor: 'rgba(255, 159, 64, 1)',
                            tension: 0.1,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
            
            // Fetch data every second
            function updateCharts() {
                fetch('/api/metrics/')
                    .then(response => response.json())
                    .then(data => {
                        // Update display values
                        document.getElementById('cpu-usage').textContent = data.cpu.toFixed(1);
                        document.getElementById('memory-usage').textContent = data.memory.toFixed(1);
                        document.getElementById('requests-processed').textContent = data.total_requests;
                        document.getElementById('requests-per-sec').textContent = data.requests_per_sec.toFixed(2);
                        document.getElementById('avg-response-time').textContent = 
                            data.avg_response_time.toFixed(2);
                        
                        // Update system chart
                        if (systemChart.data.labels.length > 20) {
                            systemChart.data.labels.shift();
                            systemChart.data.datasets[0].data.shift();
                            systemChart.data.datasets[1].data.shift();
                        }
                        
                        const now = new Date();
                        const timeString = now.getHours() + ':' + now.getMinutes() + ':' + now.getSeconds();
                        
                        systemChart.data.labels.push(timeString);
                        systemChart.data.datasets[0].data.push(data.cpu);
                        systemChart.data.datasets[1].data.push(data.memory);
                        systemChart.update();
                        
                        // Update response time chart
                        if (data.response_times.length > 0) {
                            if (responseChart.data.labels.length > 30) {
                                responseChart.data.labels.shift();
                                responseChart.data.datasets[0].data.shift();
                            }
                            
                            responseChart.data.labels.push(timeString);
                            responseChart.data.datasets[0].data.push(
                                data.response_times[data.response_times.length - 1]
                            );
                            responseChart.update();
                        }
                        
                        // Update requests per second chart
                        if (rpsChart.data.labels.length > 20) {
                            rpsChart.data.labels.shift();
                            rpsChart.data.datasets[0].data.shift();
                        }
                        
                        rpsChart.data.labels.push(timeString);
                        rpsChart.data.datasets[0].data.push(data.requests_per_sec);
                        rpsChart.update();
                    })
                    .catch(error => console.error('Error fetching metrics:', error));
            }
            
            // Update immediately and then every second
            updateCharts();
            setInterval(updateCharts, 1000);
        </script>
    </body>
    </html>
    """

# Add metrics API endpoint
@app.get("/api/metrics/")
async def get_metrics():
    # Record current system metrics
    cpu_percent = psutil.cpu_percent(interval=None)
    memory_info = psutil.virtual_memory()
    memory_mb = memory_info.used / (1024 * 1024)
    
    # Calculate requests per second
    current_time = time.time()
    time_diff = current_time - metrics_history["last_request_time"]
    
    if time_diff >= 1.0:  # Update once per second
        # Store the current count for history
        metrics_history["request_count_history"].append(metrics_history["requests"])
        if len(metrics_history["request_count_history"]) > 60:  # Keep only last minute
            metrics_history["request_count_history"].pop(0)
            
        # Calculate requests per second if we have at least 2 data points
        if len(metrics_history["request_count_history"]) >= 2:
            last_count = metrics_history["request_count_history"][-2]
            current_count = metrics_history["request_count_history"][-1]
            metrics_history["requests_per_sec"] = (current_count - last_count) / time_diff
            
        metrics_history["last_request_time"] = current_time
    
    # Update metrics history
    if len(metrics_history["timestamps"]) > 60:  # Keep only last minute
        metrics_history["timestamps"].pop(0)
        metrics_history["cpu"].pop(0)
        metrics_history["memory"].pop(0)
        
    metrics_history["timestamps"].append(time.time())
    metrics_history["cpu"].append(cpu_percent)
    metrics_history["memory"].append(memory_mb)
    
    # Return current metrics
    return {
        "cpu": cpu_percent,
        "memory": memory_mb,
        "total_requests": metrics_history["requests"],
        "requests_per_sec": metrics_history["requests_per_sec"],
        "avg_response_time": sum(metrics_history["response_times"]) / len(metrics_history["response_times"]) if metrics_history["response_times"] else 0,
        "response_times": metrics_history["response_times"][-50:] if metrics_history["response_times"] else []
    }

# Middleware to track response times
@app.middleware("http")
async def add_metrics(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000  # ms
    
    # Don't track metrics requests themselves
    if not request.url.path.startswith(("/api/metrics", "/metrics", "/dashboard")):
        metrics_history["requests"] += 1
        metrics_history["response_times"].append(process_time)
        # Keep only last 1000 response times
        if len(metrics_history["response_times"]) > 1000:
            metrics_history["response_times"].pop(0)
    
    return response

@app.post("/api/v1/users", response_model=USER_SCHEMA_OUT, status_code=status.HTTP_201_CREATED)
def create_user(user_data: USER_SCHEMA_IN, db: Session = Depends(getSession)):

    start_time  = time.time()
    
    new_user    = User(
        name        = user_data.name,
        first_name  = user_data.first_name,
        last_name   = user_data.last_name
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    processing_time = time.time() - start_time
    logger.info(f"Create user processing time: {processing_time:.6f} seconds")
    
    return new_user


@app.post("/api/v1/users/{user_id}/pets", response_model=PET_SCHEMA_OUT, status_code=status.HTTP_201_CREATED)
def add_pet_to_user(user_id: uuid.UUID, pet_data: PET_SCHEMA_IN, db: Session = Depends(getSession)):
    start_time = time.time()
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"User with id {user_id} not found when adding pet")
        raise HTTPException(status_code=404, detail="User not found")
    
    new_pet = Pet(
        user_id    = user_id,
        name        = pet_data.name,
        type        = pet_data.type,
    )
    
    db.add(new_pet)
    db.commit()
    db.refresh(new_pet)
    
    processing_time = time.time() - start_time
    logger.info(f"Add pet to user processing time: {processing_time:.6f} seconds")
    
    return new_pet


@app.get("/api/v1/users/{user_id}", response_model=USER_SCHEMA_OUT)
def get_user_with_pets(user_id: uuid.UUID, db: Session = Depends(getSession)):
    start_time  = time.time()
    
    user        = db.query(User).filter(User.id == user_id).first()

    if not user:
        logger.warning(f"User with id {user_id} not found")
        raise HTTPException(status_code=404, detail="User not found")
    
    processing_time = time.time() - start_time
    logger.info(f"Get user with pets processing time: {processing_time:.6f} seconds")
    
    return user



if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI application")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)