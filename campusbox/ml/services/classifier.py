import joblib
import pandas as pd
from django.conf import settings
from menu.models import MealCategory

MODEL_PATH = settings.BASE_DIR / "ml" / "trained_models" / "meal_category_model.joblib" #finds the saved file(trained brain) of 
#the model that was trained to predict meal categories based on student profiles
saved = joblib.load(MODEL_PATH)
model = saved["model"]
columns = saved["columns"]


def predict_preferred_category(profile): #takes a student profile and predicts the meal category that the student is most likely to prefer based on their quiz answers
    row = pd.DataFrame([{
        "age": profile.age,
        "gender": profile.gender,
        "is_on_campus": profile.is_on_campus,
        "budget_per_meal": profile.budget_per_meal,
        "fitness_goal": profile.fitness_goal,
        "spice_tolerance": profile.spice_tolerance,
        "diet": profile.diet,
    }])
    row = pd.get_dummies(row)
    row = row.reindex(columns=columns, fill_value=0)
    category_name = model.predict(row)[0] #predicts the meal category that the student is most likely to prefer based on their quiz answers
    return MealCategory.objects.filter(name=category_name).first()