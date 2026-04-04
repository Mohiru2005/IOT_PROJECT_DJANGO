import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier
import joblib
import os
from django.conf import settings

MODEL_FILE = os.path.join(settings.BASE_DIR, "climate_brain.joblib")

def train_and_save_model():
    """
    Generate synthetic data based on smarter autonomous comfort rules:
    - AC_ON: If indoor is dangerously hot (>26), OR marginally warm (>=24) but very hot outside (>=30).
    - HEATER_ON: If indoor is cold (<20), OR marginally cool (<=22) but cold outside (<=15).
    - STANDBY: Otherwise (the 20-25°C safe zone).
    """
    data = []
    for in_temp in np.arange(10, 41, 0.5):
        for out_temp in np.arange(-5, 46, 0.5):
            for hum in (30, 50, 70):
                if in_temp > 26 or (in_temp >= 24 and out_temp >= 30):
                    decision = "AC_ON"
                elif in_temp < 20 or (in_temp <= 22 and out_temp <= 15):
                    decision = "HEATER_ON"
                else:
                    decision = "STANDBY"
                data.append([in_temp, out_temp, hum, decision])
                
    df = pd.DataFrame(data, columns=["indoor_temp", "outdoor_temp", "humidity", "decision"])
    
    X = df[["indoor_temp", "outdoor_temp", "humidity"]]
    y = df["decision"]
    
    clf = DecisionTreeClassifier(max_depth=5, random_state=42)
    clf.fit(X.values, y)
    
    joblib.dump(clf, MODEL_FILE)
    print(f"Model saved to {MODEL_FILE}")
    return clf


def get_ai_decision(indoor_t, outdoor_t, humidity):
    """
    Predicts the climate control state based on the input features.
    """
    if not os.path.exists(MODEL_FILE):
        clf = train_and_save_model()
    else:
        clf = joblib.load(MODEL_FILE)
        
    prediction = clf.predict([[indoor_t, outdoor_t, humidity]])[0]
    return prediction
