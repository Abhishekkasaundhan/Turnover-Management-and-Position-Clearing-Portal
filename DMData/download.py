from flask import Flask, send_file
import pandas as pd
import os

app = Flask(__name__)

@app.route('/download')
def download():
    # Generate or load your DataFrame here
    df = pd.DataFrame({
        'Symbol': ['AAPL', 'GOOG'],
        'Expiry': ['2024-08-01', '2024-08-02'],
        'Strike': [150.0, 2800.0],
        'Option Type': ['Call', 'Put'],
        'Net Quantity': [100, -50],
        'Buy Quantity': [150, 0],
        'Sell Quantity': [50, 50]
    })

    # Define path and filename
    folder_path = r""
    file_path = os.path.join(folder_path, "clearing.xlsx")

    # Ensure folder exists
    os.makedirs(folder_path, exist_ok=True)

    # Save DataFrame to Excel
    df.to_excel(file_path, index=False)

    return send_file(file_path, as_attachment=True)
