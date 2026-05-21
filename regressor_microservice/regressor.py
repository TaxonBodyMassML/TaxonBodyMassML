"""
pasquang
pasquang@oregonstate.edu
4/10/2026
"""

#run using: gunicorn -w 1 -b 127.0.0.1:8000 'regressor:create_wsgi_app()'

import numpy as np
import pandas as pd
import xgboost as xgb
import pickleslicer
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import traceback


MODEL_READ_FILE = './sliced_model/xgboost_model.pkl'

def align_categories(train_df, test_df):
    """
    This function ensures that both the test and training set contain
    all unique categories from both sets for each column.
    It also adds

    Args:
        train_df (pandas dataframe): _description_
        test_df (pandas dataframe): _description_

    Returns:
        a tuple of the reformatted x_train and x_test with shared categories and UNK added
    """
    for col in train_df.select_dtypes(include="object").columns:
        train_df[col] = train_df[col].astype("category")
        test_df[col] = test_df[col].astype("category")

        # adds the UNK category and both train and test categories
        categories = list(set(train_df[col].cat.categories) |
                          set(list(test_df[col].cat.categories)) |
                          {"UNK"})

        train_df[col] = train_df[col].cat.set_categories(categories)
        test_df[col] = test_df[col].cat.set_categories(categories)

    return train_df, test_df

def parse_dataset():
    # import training and testing data
    train = pd.read_csv("./data/train.csv")
    test = pd.read_csv("./data/test.csv")

    # convert mass to log10 to avoid rounding error
    # + reduce loss effect of large outliers
    train["mass_g"] = np.log10(train["mass_g"])
    test["mass_g"] = np.log10(test["mass_g"])

    #print("The Training Data is\n", train.head())
    #print("The Testing Data is\n", test.head())

    # needs to remove other data when full taxonomy is created
    # keep and remove labels from training and test data

    #y_train = train["mass_g"]
    x_train = train.drop(["mass_g"], axis=1)

    #y_test = test["mass_g"]
    x_test = test.drop(["mass_g"], axis=1)
    
    return x_train, x_test

def create_app(loaded_model, x_train, q):
    app = Flask(__name__)
    CORS(app)

    app.config["model"] = loaded_model
    app.config["q"] = q
    app.config["x_train"] = x_train
    
    @app.route("/xgb_pred_single", methods=["POST"])
    def xgb_pred_single():
        
        try:
            model = app.config["model"]
            x_train = app.config["x_train"]

            data = request.json
            df = pd.DataFrame([data])
            
            print("Input query:\n", df)
            print(df["species"].isin(x_train["species"].cat.categories))
            for col in df.columns:
                if col in x_train.columns and (df[col].dtype.name == "object" or df[col].dtype.name == "str"):
                    df[col] = df[col].where(df[col].isin(x_train[col].cat.categories), other="UNK")

            _, df = align_categories(x_train.copy(), df)
            
            for col in df.select_dtypes(include="object").columns:
                df[col] = df[col].astype("category")
            
            print(df)
            
            prediction_log = model.predict(df)[0]
            q = app.config["q"]

            lower_pred = prediction_log - q
            upper_pred = prediction_log + q

            prediction = float(10 ** prediction_log)
            lower = float(10 ** lower_pred)
            upper = float(10 ** upper_pred)
            
            return jsonify({
                "taxonomy": {
                    "kingdom": df["kingdom"].iloc[0],
                    "phylum": df["phylum"].iloc[0],
                    "class": df["class"].iloc[0],
                    "order": df["order"].iloc[0],
                    "family": df["family"].iloc[0],
                    "genus": df["genus"].iloc[0],
                    "species": df["species"].iloc[0],
                },
                "prediction": prediction,
                "lower_bound": lower,
                "upper_bound": upper,
                "confidence": 0.90
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({
                "error": str(e)
            }), 500
    
    @app.route("/xgb_pred_multi", methods=["POST"])
    def xgb_pred_multi():
        
        model = app.config["model"]
        x_train = app.config["x_train"]

        data = request.json
        df = pd.DataFrame(data)
        
        print("Input query:\n", df)
        
        for col in df.columns:
            if col in x_train.columns and (df[col].dtype.name == "object" or df[col].dtype.name == "str"):
                df[col] = df[col].where(
                    df[col].isin(x_train[col].cat.categories),
                    other="UNK"
                )

        _, df = align_categories(x_train.copy(), df)
        
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype("category")
        
        print(df)
        
        predictions = model.predict(df)
        results = []
        for row, pred in zip(df.to_dict(orient="records"), predictions):
            
            q = app.config["q"]

            lower_pred = pred - q
            upper_pred = pred + q

            prediction = float(10 ** pred)
            lower = float(10 ** lower_pred)
            upper = float(10 ** upper_pred)
        
            
            results.append({
                "taxonomy": {
                    "kingdom": row.get("kingdom"),
                    "phylum": row.get("phylum"),
                    "class": row.get("class"),
                    "order": row.get("order"),
                    "family": row.get("family"),
                    "genus": row.get("genus"),
                    "species": row.get("species"),
                },
                "prediction": prediction,
                "lower_bound": lower,
                "upper_bound": upper,
                "confidence": 0.90
            })
            
        return jsonify({"items" : results})

    @app.route("/", methods=["GET"])
    def home():
        return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Model API</title>
        </head>
        <body>
            <h1>Model server is running!</h1>\
        </body>
    </html>
    
    """
    
    print(app.url_map)
    return app

def main():
    
    loaded_bundle = pickleslicer.load(MODEL_READ_FILE)
    
    loaded_model = loaded_bundle["model"]
    q = loaded_bundle["q"]
        
    if not loaded_model:
        print("Model not loaded successfully.")
        exit(1)
    else:
        print("Model loaded successfully.")
        
    x_train, x_test = parse_dataset()
    x_train, x_test = align_categories(x_train, x_test)
    
    app = create_app(loaded_model, x_train, q)
    print("App running...")
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


def create_wsgi_app():
    
    loaded_bundle = pickleslicer.load(MODEL_READ_FILE)
    
    loaded_model = loaded_bundle["model"]
    q = loaded_bundle["q"]
        
    if not loaded_model:
        print("Model not loaded successfully.")
        exit(1)
    else:
        print("Model loaded successfully.")
        
    x_train, x_test = parse_dataset()
    x_train, x_test = align_categories(x_train, x_test)
    
    return create_app(loaded_model, x_train, q)
    

if __name__ == "__main__":
    main()
