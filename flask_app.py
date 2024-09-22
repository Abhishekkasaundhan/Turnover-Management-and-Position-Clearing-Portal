import os
import glob
import logging
from flask import Flask, request, render_template, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

class LoginForm(FlaskForm):
    group_name = StringField('Groups', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class User(UserMixin):
    def __init__(self, id):
        self.id = id

group_data = {}
GROUP_COLUMN1 = 'Main & Sub Users'
FLASH_APP_PATH = os.path.dirname(os.path.abspath(__file__))
DM_DATA_PATH = os.path.join(FLASH_APP_PATH, 'DMData')

def get_skip_folders():
    if current_user.is_authenticated:
        return {current_user.id}
    return set()

def read_groups():
    groups = {}
    file_path = glob.glob(os.path.join(FLASH_APP_PATH, r'credential\*.xlsx'))[0]
    df = pd.read_excel(file_path)
    for _, row in df.iterrows():
        group = row['Groups']
        password = str(row['Password'])
        pro_client = row['Pro Client']
        groups[group] = {
            'password': generate_password_hash(password),
            'pro_client': pro_client
        }
    logging.info(f"Groups loaded: {groups}")
    return groups

group_data = read_groups()

@login_manager.user_loader
def load_user(user_id):
    return User(user_id) if user_id in group_data else None

@app.route('/')
def index():
    form = LoginForm()
    return render_template('login.html', form=form)

@app.route('/login', methods=['POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        group_name = form.group_name.data
        password = form.password.data

        global group_data
        group_data = read_groups()

        if group_name in group_data and check_password_hash(group_data[group_name]['password'], password):
            user = User(group_name)
            login_user(user)

            # Ensure user folder exists
            user_folder_path = os.path.join(DM_DATA_PATH, group_name)
            if not os.path.exists(user_folder_path):
                os.makedirs(user_folder_path)
                logging.info(f"Created new folder for user: {group_name} at {user_folder_path}")

            return redirect(url_for('data', group_name=group_name))
        else:
            return render_template('login.html', form=form, error='Invalid User Name or Password')
    return render_template('login.html', form=form)

@app.route('/data/<group_name>')
@login_required
def data(group_name):
    if group_name != current_user.id:
        return redirect(url_for('index'))

    def read_files():
        file_paths = glob.glob(os.path.join(FLASH_APP_PATH, r'Data\*.xlsx')) + glob.glob(os.path.join(FLASH_APP_PATH, r'Data\*.csv'))
        data_frames = []
        for file_path in file_paths:
            if file_path.endswith('.xlsx'):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path)
            data_frames.append(df)
        return data_frames

    data_frames = read_files()
    columns = request.args.get('columns', None)
    if columns:
        columns = columns.split(',')

    def replace_nan(df):
        df.fillna('-', inplace=True)
        return df

    data_frames = [replace_nan(df) for df in data_frames]

    def filter_by_group(df, group_name):
        df[GROUP_COLUMN1] = df[GROUP_COLUMN1].astype(str)
        filtered_df = df[df[GROUP_COLUMN1].apply(lambda x: any(g.strip() == group_name for g in x.split(',')) or 'ALL' in x)]
        return filtered_df

    filtered_data_frames = [filter_by_group(df, group_name) for df in data_frames]

    def format_data(df, columns):
        data = df.to_dict(orient='records')
        for row in data:
            for column in columns:
                if pd.isna(row[column]):
                    row[column] = '-'
                elif isinstance(row[column], float) and row[column].is_integer():
                    row[column] = int(row[column])
        return data

    formatted_data = [format_data(df, df.columns) for df in filtered_data_frames]

    data_files = glob.glob(os.path.join(FLASH_APP_PATH, r'Data\*.xlsx')) + glob.glob(os.path.join(FLASH_APP_PATH, r'Data\*.csv'))
    data_files = [os.path.basename(file) for file in data_files]

    return render_template('index.html', group_name=group_name, 
                           all_columns=[df.columns.tolist() for df in data_frames],  
                           data=formatted_data,
                           data_files=data_files)

@app.route('/turnover')
@login_required
def turnover():
    def get_user_path(user_id):
        user_paths = {
            current_user.id: os.path.join(DM_DATA_PATH, current_user.id)
        }
        return user_paths.get(user_id, '')

    def read_header_possibilities():
        header_path = os.path.join(DM_DATA_PATH, 'Header_possibilities.xlsx')
        df = pd.read_excel(header_path)
        header_mapping = df.to_dict(orient='list')
        return header_mapping

    def read_columns_data_possibilities():
        file_path = os.path.join(DM_DATA_PATH, 'Columns_data_possibilities.xlsx')
        df = pd.read_excel(file_path)
        return df['Future Value'].dropna().tolist(), df['Option Value'].dropna().tolist()
    
    header_mapping = read_header_possibilities()
    future_values, option_values = read_columns_data_possibilities()

    def match_and_calculate(folder_path, header_mapping, future_values, option_values, pro_client_value):
        folder_totals = []
        all_users = set()  

        if pro_client_value is None or pd.isna(pro_client_value):
            pro_client_value = ''
        else:
            pro_client_value = str(pro_client_value)

        pro_client_values = [value.strip() for value in pro_client_value.split('|')] if pro_client_value else []

        for subdir, _, _ in os.walk(folder_path):
            folder_name = os.path.basename(subdir)
            if folder_name in get_skip_folders():
                continue

            totals = {
                'Date': folder_name,
                'EQ Buy Value': 0,
                'EQ Sell Value': 0,
                'Future Buy Value': 0,
                'Option Buy Value': 0,
                'Future Sell Value': 0,
                'Option Sell Value': 0,
                'Buy Quantity': 0,
                'Sell Quantity': 0,
                'Trading ID': ''  # Updated column name
            }
            all_users = set()

            for file_path in glob.glob(os.path.join(subdir, '*'), recursive=True):
                if file_path.endswith(('.xls', '.xlsx', '.csv')):
                    if file_path.endswith('.xlsx'):
                        df = pd.read_excel(file_path)
                    elif file_path.endswith('.xls'):
                        df = pd.read_csv(file_path, sep='\t')
                    else:
                        df = pd.read_csv(file_path)

                    # Normalize header names
                    for col, possible_names in header_mapping.items():
                        for name in possible_names:
                            if name in df.columns:
                                df.rename(columns={name: col}, inplace=True)
                                break

                    if 'Client Name' in df.columns:
                        df = df[df['Client Name'].astype(str).apply(
                            lambda x: any(client == value or client == str(value) for value in x.split('|') for client in pro_client_values)
                        )]

                    if 'name' in df.columns:
                        df.dropna(subset=['name'], inplace=True)

                    # Collect unique users
                    if 'User' in df.columns:
                        unique_users = df['User'].dropna().astype(str).unique()
                        all_users.update(unique_users)

                    # Process the data in each row
                    for _, row in df.iterrows():
                        option_type = str(row.get('Option Type', '')).strip()
                        market_segment = str(row.get('Market Segment', '')).strip()

                        if option_type in future_values:
                            totals['Future Buy Value'] += row.get('Buy Value', 0)
                            totals['Future Sell Value'] += row.get('Sell Value', 0)
                            totals['Buy Quantity'] += row.get('Buy Quantity', 0)
                            totals['Sell Quantity'] += row.get('Sell Quantity', 0)
                        elif option_type in option_values:
                            totals['Option Buy Value'] += row.get('Buy Value', 0)
                            totals['Option Sell Value'] += row.get('Sell Value', 0)
                            totals['Buy Quantity'] += row.get('Buy Quantity', 0)
                            totals['Sell Quantity'] += row.get('Sell Quantity', 0)
                        elif option_type and market_segment == 'F':
                            totals['Future Buy Value'] += row.get('Buy Value', 0)
                            totals['Future Sell Value'] += row.get('Sell Value', 0)
                            totals['Buy Quantity'] += row.get('Buy Quantity', 0)
                            totals['Sell Quantity'] += row.get('Sell Quantity', 0)
                        elif option_type and market_segment == 'E':
                            totals['EQ Buy Value'] += row.get('Buy Value', 0)
                            totals['EQ Sell Value'] += row.get('Sell Value', 0)
                            totals['Buy Quantity'] += row.get('Buy Quantity', 0)
                            totals['Sell Quantity'] += row.get('Sell Quantity', 0)

            # Add the concatenated user values to totals
            totals['Trading ID'] = ' | '.join(sorted(all_users))
            folder_totals.append(totals)

        return folder_totals

    user_path = get_user_path(current_user.id)
    if not user_path:
        return redirect(url_for('index'))

    pro_client_value = group_data[current_user.id]['pro_client']
    turnover_data = match_and_calculate(user_path, header_mapping, future_values, option_values, pro_client_value)

    total_future_buy_value = sum(row['Future Buy Value'] for row in turnover_data)
    total_option_buy_value = sum(row['Option Buy Value'] for row in turnover_data)
    total_EQ_buy_value = sum(row['EQ Buy Value'] for row in turnover_data)
    total_future_sell_value = sum(row['Future Sell Value'] for row in turnover_data)
    total_option_sell_value = sum(row['Option Sell Value'] for row in turnover_data)
    total_EQ_sell_value = sum(row['EQ Sell Value'] for row in turnover_data)
    total_buy_quantity = sum(row['Buy Quantity'] for row in turnover_data)
    total_sell_quantity = sum(row['Sell Quantity'] for row in turnover_data)

    return render_template('turnover.html',
                           turnover_data=turnover_data,
                           total_future_buy_value=total_future_buy_value,
                           total_option_buy_value=total_option_buy_value,
                           total_EQ_buy_value=total_EQ_buy_value,
                           total_future_sell_value=total_future_sell_value,
                           total_option_sell_value=total_option_sell_value,
                           total_EQ_sell_value=total_EQ_sell_value,
                           total_buy_quantity=total_buy_quantity,
                           total_sell_quantity=total_sell_quantity,
                           group_name=current_user.id)


from flask import redirect, url_for, render_template
from flask_login import login_required, current_user
import os
import pandas as pd
import glob
from datetime import datetime

@app.route('/position')
@login_required
def position():
    def read_header_possibilities():
        header_path = os.path.join(DM_DATA_PATH, 'Header_possibilities.xlsx')
        df = pd.read_excel(header_path)
        header_mapping = df.to_dict(orient='list')
        return header_mapping
    
    header_mapping = read_header_possibilities()

    def get_user_path(user_id):
        user_paths = {
            current_user.id: os.path.join(DM_DATA_PATH, current_user.id)
        }
        return user_paths.get(user_id, '')

    def read_columns_data_possibilities():
        file_path = os.path.join(DM_DATA_PATH, 'Columns_data_possibilities.xlsx')
        df = pd.read_excel(file_path)
        return df['Future Value'].dropna().tolist(), df['Option Value'].dropna().tolist()

    future_values, option_values = read_columns_data_possibilities()

    def read_lot_sizes():
        lot_size_path = os.path.join(DM_DATA_PATH, 'LOTSIZE', 'LOTSIZE.xlsx')  # Update the file name as necessary
        df = pd.read_excel(lot_size_path)
        lot_size_mapping = df.set_index('Symbol')['Lot Size'].to_dict()  # Create a dictionary for easy lookup
        return lot_size_mapping

    lot_size_mapping = read_lot_sizes()

    def match_and_calculate(folder_path, header_mapping, future_values, option_values, pro_client_value):
        position_data = []

        # Normalize the pro_client_value
        if isinstance(pro_client_value, (float, int)):
            pro_client_value = str(pro_client_value)
        elif pro_client_value is None or pd.isna(pro_client_value):
            pro_client_value = ''
        pro_client_values = [value.strip() for value in pro_client_value.split('|')] if pro_client_value else []

        for subdir, _, _ in os.walk(folder_path):
            folder_name = os.path.basename(subdir)
            if folder_name in get_skip_folders():
                continue

            for file_path in glob.glob(os.path.join(subdir, '*'), recursive=True):
                if file_path.endswith(('.xls', '.xlsx', '.csv')):
                    # Read the file
                    if file_path.endswith('.xlsx'):
                        df = pd.read_excel(file_path)
                    elif file_path.endswith('.xls'):
                        df = pd.read_csv(file_path, sep='\t')
                    else:
                        df = pd.read_csv(file_path)

                    # Rename columns based on header_mapping
                    for col, possible_names in header_mapping.items():
                        for name in possible_names:
                            if name in df.columns:
                                df.rename(columns={name: col}, inplace=True)
                                break

                    # Filter 'Client Name' if it exists
                    if 'Client Name' in df.columns:
                        df = df[df['Client Name'].astype(str).apply(
                            lambda x: any(client == value for value in x.split('|') for client in pro_client_values)
                        )]

                    # Drop rows with empty 'name' and handle 'Expiry' values
                    if 'name' in df.columns:
                        df.dropna(subset=['name'], inplace=True)
                    if 'Expiry' in df.columns:
                        df['Expiry'].fillna('-', inplace=True)

                    # Implement the provided portion of code
                    mask = df['Option Type'].isin(future_values)
                    grouped_mask = df[mask].groupby(['Symbol', 'Expiry'], as_index=False).agg({
                        'Net Quantity': 'sum'
                    })
                    grouped_mask['Strike'] = '-0.01'
                    grouped_mask['Option Type'] = 'FUT'

                    df = pd.concat([df[~mask], grouped_mask], ignore_index=True)

                    # Iterate over rows to construct position data
                    for _, row in df.iterrows():
                        symbol = row.get('Symbol', '-')
                        expiry = row.get('Expiry', '-')
                        strike = row.get('Strike', '-')
                        option_type = row.get('Option Type', '-')
                        market_segment = row.get('Market Segment', '-') 
                        net_lot = row.get('Net Lot', '-')


                        # Apply additional logic for option_type and market_segment
                        if expiry == 'EQ':
                            strike = '-0.01'
                            option_type = 'EQ'
                        else:
                            # Existing logic for other cases
                            market_segment = str(row.get('Market Segment', '')).strip()
                            if option_type and market_segment == 'F':
                                strike = '-0.01'
                                option_type = 'FUT'
                            elif option_type and market_segment == 'E':
                                strike = '-0.01'
                                option_type = 'EQ'
                        net_quantity = row.get('Net Quantity', 0)

                        position_data.append({
                            'Symbol': symbol,
                            'Expiry': expiry,
                            'Strike': strike,
                            'Option Type': option_type,
                            'Net Quantity': net_quantity,
                            'Net Lot': net_lot

                        })

        df_grouped = pd.DataFrame(position_data)

        # Ensure all required columns are present
        required_columns = ['Symbol', 'Strike', 'Option Type', 'Expiry']
        for col in required_columns:
            if col not in df_grouped.columns:
                df_grouped[col] = '-'

        # Convert 'Expiry' to a standard date format
        def convert_expiry(val):
            try:
                date = pd.to_datetime(val, unit='D', origin='1899-12-30')
            except (ValueError, TypeError):
                try:
                    date = pd.to_datetime(val)
                except Exception:
                    return val
            return date.strftime('%Y-%m-%d')

        df_grouped['Expiry'] = df_grouped['Expiry'].apply(convert_expiry)

        # Group and sum data by the key columns
        df_grouped = df_grouped.groupby(['Symbol', 'Expiry', 'Strike', 'Option Type'], as_index=False).sum()

        # Handle empty DataFrame case
        if df_grouped.empty:
            df_grouped = pd.DataFrame([{
                'Symbol': '-',
                'Expiry': '-',
                'Strike': '-',
                'Option Type': '-',
                'Net Quantity': 0,
                'Buy Quantity': 0,
                'Sell Quantity': 0
            }])



        df_grouped['Net Lot'] = df_grouped.apply(
            lambda row: row['Net Quantity'] / lot_size_mapping.get(row['Symbol'], 1) if row['Symbol'] in lot_size_mapping else '-',
            axis=1
        )

        return df_grouped

    user_path = get_user_path(current_user.id)
    if not user_path:
        return redirect(url_for('index'))

    pro_client_value = group_data[current_user.id]['pro_client']
    position_data = match_and_calculate(user_path, header_mapping, future_values, option_values, pro_client_value)
    
    return render_template('position.html', position_data=position_data, group_name=current_user.id)



from flask import redirect, url_for, render_template
from flask_login import login_required, current_user
import os
import pandas as pd
import glob
from datetime import datetime

@app.route('/clearing')
@login_required
def clearing():
    def read_header_possibilities():
        header_path = os.path.join(DM_DATA_PATH, 'Header_possibilities.xlsx')
        df = pd.read_excel(header_path)
        header_mapping = df.to_dict(orient='list')
        return header_mapping
    
    header_mapping = read_header_possibilities()

    def get_user_path(user_id):
        user_paths = {
            current_user.id: os.path.join(DM_DATA_PATH, current_user.id)
        }
        return user_paths.get(user_id, '')

    def read_columns_data_possibilities():
        file_path = os.path.join(DM_DATA_PATH, 'Columns_data_possibilities.xlsx')
        df = pd.read_excel(file_path)
        return df['Future Value'].dropna().tolist(), df['Option Value'].dropna().tolist()

    future_values, option_values = read_columns_data_possibilities()

    def match_and_calculate(folder_path, header_mapping, future_values, option_values, pro_client_value):
        position_data = []

        # Normalize the pro_client_value
        if isinstance(pro_client_value, (float, int)):
            pro_client_value = str(pro_client_value)
        elif pro_client_value is None or pd.isna(pro_client_value):
            pro_client_value = ''
        pro_client_values = [value.strip() for value in pro_client_value.split('|')] if pro_client_value else []

        for subdir, _, _ in os.walk(folder_path):
            folder_name = os.path.basename(subdir)
            if folder_name in get_skip_folders():
                continue

            for file_path in glob.glob(os.path.join(subdir, '*'), recursive=True):
                if file_path.endswith(('.xls', '.xlsx', '.csv')):
                    # Read the file
                    if file_path.endswith('.xlsx'):
                        df = pd.read_excel(file_path)
                    elif file_path.endswith('.xls'):
                        df = pd.read_csv(file_path, sep='\t')
                    else:
                        df = pd.read_csv(file_path)

                    # Rename columns based on header_mapping
                    for col, possible_names in header_mapping.items():
                        for name in possible_names:
                            if name in df.columns:
                                df.rename(columns={name: col}, inplace=True)
                                break

                    # Filter 'Client Name' if it exists
                    if 'Client Name' in df.columns:
                        df = df[df['Client Name'].astype(str).apply(
                            lambda x: any(client == value for value in x.split('|') for client in pro_client_values)
                        )]

                    # Drop rows with empty 'name' and handle 'Expiry' values
                    if 'name' in df.columns:
                        df.dropna(subset=['name'], inplace=True)
                    if 'Expiry' in df.columns:
                        df['Expiry'].fillna('-', inplace=True)

                    # Implement the provided portion of code
                    mask = df['Option Type'].isin(future_values)
                    grouped_mask = df[mask].groupby(['Symbol', 'Expiry'], as_index=False).agg({
                        'Net Quantity': 'sum'
                    })
                    grouped_mask['Strike'] = '-0.01'
                    grouped_mask['Option Type'] = 'FUT'

                    df = pd.concat([df[~mask], grouped_mask], ignore_index=True)

                    # Iterate over rows to construct position data
                    for _, row in df.iterrows():
                        symbol = row.get('Symbol', '-')
                        expiry = row.get('Expiry', '-')
                        strike = row.get('Strike', '-')
                        option_type = row.get('Option Type', '-')
                        market_segment = row.get('Market Segment', '-')  # Ensure this is the correct column name

                        # Apply additional logic for option_type and market_segment
                        if expiry == 'EQ':
                            strike = '-0.01'
                            option_type = 'EQ'
                        else:
                            # Existing logic for other cases
                            market_segment = str(row.get('Market Segment', '')).strip()
                            if option_type and market_segment == 'F':
                                strike = '-0.01'
                                option_type = 'FUT'
                            elif option_type and market_segment == 'E':
                                strike = '-0.01'
                                option_type = 'EQ'
                        net_quantity = row.get('Net Quantity', 0)

                        position_data.append({
                            'Symbol': symbol,
                            'Expiry': expiry,
                            'Strike': strike,
                            'Option Type': option_type,
                            'Net Quantity': net_quantity
                        })

        df_grouped = pd.DataFrame(position_data)

        # Ensure all required columns are present
        required_columns = ['Symbol', 'Strike', 'Option Type', 'Expiry']
        for col in required_columns:
            if col not in df_grouped.columns:
                df_grouped[col] = '-'

        # Convert 'Expiry' to a standard date format
        def convert_expiry(val):
            try:
                date = pd.to_datetime(val, unit='D', origin='1899-12-30')
            except (ValueError, TypeError):
                try:
                    date = pd.to_datetime(val)
                except Exception:
                    return val
            return date.strftime('%Y-%m-%d')

        df_grouped['Expiry'] = df_grouped['Expiry'].apply(convert_expiry)

        # Group and sum data by the key columns
        df_grouped = df_grouped.groupby(['Symbol', 'Expiry', 'Strike', 'Option Type'], as_index=False).sum()

        # Handle empty DataFrame case
        if df_grouped.empty:
            df_grouped = pd.DataFrame([{
                'Symbol': '-',
                'Expiry': '-',
                'Strike': '-',
                'Option Type': '-',
                'Net Quantity': 0,
                'Buy Quantity': 0,
                'Sell Quantity': 0
            }])

        # Reverse the sign of 'Net Quantity' and filter by expiry date
        df_grouped['Net Quantity'] = df_grouped['Net Quantity'] * -1
        today = datetime.now().strftime('%Y-%m-%d')
        df_grouped = df_grouped[df_grouped['Expiry'] < today]

        # Calculate 'Buy Quantity' and 'Sell Quantity'
        df_grouped['Buy Quantity'] = df_grouped['Net Quantity'].apply(lambda x: x if x > 0 else 0)
        df_grouped['Sell Quantity'] = df_grouped['Net Quantity'].apply(lambda x: abs(x) if x < 0 else 0)

        return df_grouped

    user_path = get_user_path(current_user.id)
    if not user_path:
        return redirect(url_for('index'))

    pro_client_value = group_data[current_user.id]['pro_client']
    position_data = match_and_calculate(user_path, header_mapping, future_values, option_values, pro_client_value)
    
    return render_template('clearing.html', position_data=position_data, group_name=current_user.id)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    group_name = current_user.id
    selected_date = None
    message = None
    files = []
    folder_path = None

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'list_files':
            selected_date = request.form.get('manage_datepicker')
            if selected_date:
                try:
                    folder_name = selected_date.replace('-', '-')
                    folder_path = os.path.join(DM_DATA_PATH, group_name, folder_name)
                    if os.path.isdir(folder_path):
                        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                    else:
                        message = f"Folder for date '{selected_date}' not found."
                except Exception as e:
                    message = f"Error: {str(e)}"

        elif action == 'delete_files':
            delete_date = request.form.get('delete_datepicker')
            files_to_delete = request.form.getlist('files_to_delete')

            if delete_date:
                try:
                    folder_name = delete_date.replace('-', '-')
                    folder_path = os.path.join(DM_DATA_PATH, group_name, folder_name)
                    if os.path.isdir(folder_path):
                        for file in files_to_delete:
                            file_path = os.path.join(folder_path, file)
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                        message = "Selected files deleted successfully."
                    else:
                        message = f"Folder for date '{delete_date}' not found."
                except Exception as e:
                    message = f"Error: {str(e)}"

        else:
            selected_date = request.form.get('datepicker')
            if selected_date:
                try:
                    folder_name = selected_date.replace('-', '-')
                    folder_path = os.path.join(DM_DATA_PATH, group_name, folder_name)
                    os.makedirs(folder_path, exist_ok=True)

                    uploaded_files = request.files.getlist('files[]')
                    for file in uploaded_files:
                        if file.filename:
                            file_path = os.path.join(folder_path, file.filename)
                            file.save(file_path)
                    message = f"{len(uploaded_files)} file(s) uploaded successfully to '{folder_name}'."
                except Exception as e:
                    message = f"Error: {str(e)}"

    return render_template('upload.html', selected_date=selected_date, message=message, files=files, group_name=group_name)


from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory

@app.route('/download/<date>/<filename>')
@login_required
def download_file(date, filename):
    group_name = current_user.id
    folder_name = date.replace('-', '-')
    folder_path = os.path.join(DM_DATA_PATH, group_name, folder_name)
    return send_from_directory(folder_path, filename)


from flask import Flask, render_template, redirect, url_for
import os
import pandas as pd


from datetime import datetime

@app.route('/position1')
@login_required
def position1():
    def read_header_possibilities():
        header_path = os.path.join(DM_DATA_PATH, 'Header_possibilities.xlsx')
        df = pd.read_excel(header_path)
        header_mapping = df.to_dict(orient='list')
        return header_mapping

    header_mapping = read_header_possibilities()

    def get_user_path(user_id):
        return os.path.join(DM_DATA_PATH, user_id) if user_id else ''

    def read_columns_data_possibilities():
        file_path = os.path.join(DM_DATA_PATH, 'Columns_data_possibilities.xlsx')
        df = pd.read_excel(file_path)
        return df['Future Value'].dropna().tolist(), df['Option Value'].dropna().tolist()

    future_values, option_values = read_columns_data_possibilities()

    def match_and_calculate(folder_path, header_mapping, future_values, option_values, pro_client_value):
        position_data = []
        pro_client_values = [value.strip() for value in str(pro_client_value).split('|') if pro_client_value]

        for subdir, _, _ in os.walk(folder_path):
            folder_name = os.path.basename(subdir)
            if folder_name in get_skip_folders():
                continue

            for file_path in glob.glob(os.path.join(subdir, '*')):
                if file_path.endswith(('.xls', '.xlsx', '.csv')):
                    if file_path.endswith('.xlsx'):
                        df = pd.read_excel(file_path)
                    elif file_path.endswith('.xls'):
                        df = pd.read_csv(file_path, sep='\t')
                    else:
                        df = pd.read_csv(file_path)

                    # Renaming columns according to header_mapping
                    for col, possible_names in header_mapping.items():
                        for name in possible_names:
                            if name in df.columns:
                                df.rename(columns={name: col}, inplace=True)
                                break

                    if 'Client Name' in df.columns:
                        df = df[df['Client Name'].astype(str).apply(
                            lambda x: any(client == value for value in x.split('|') for client in pro_client_values)
                        )]

                    # Processing rows only if necessary columns are present
                    if 'Symbol' in df.columns and 'Net Quantity' in df.columns and 'Option Type' in df.columns:
                        df.dropna(subset=['Symbol'], inplace=True)

                        # Remove rows where the 'Expiry' date has already passed
                        if 'Expiry' in df.columns:
                            df['Expiry'] = pd.to_datetime(df['Expiry'], errors='coerce')
                            today = datetime.today()
                            df = df[df['Expiry'] > today]

                        for _, row in df.iterrows():
                            symbol = row.get('Symbol', '-')
                            option_type = row.get('Option Type', '-')
                            net_quantity = row.get('Net Quantity', 0)
                            market_segment = str(row.get('Market Segment', '')).strip()
                            
                            # Initialize a dictionary for each symbol with all columns
                            position_entry = {'Symbol': symbol, 'CE': 0, 'PE': 0, 'FUT': 0, 'EQ': 0}

                            if option_type in future_values or (market_segment == 'F' and option_type):
                                position_entry['FUT'] = net_quantity
                            elif market_segment == 'E' and option_type:
                                position_entry['EQ'] = net_quantity
                            elif option_type == 'CE' or option_type == 'C':
                                position_entry['CE'] = net_quantity
                            elif option_type == 'PE' or option_type == 'P':
                                position_entry['PE'] = net_quantity
                            else:
                                continue

                            # Append the correctly structured data
                            position_data.append(position_entry)

        # Convert list to DataFrame and group by 'Symbol'
        df_position = pd.DataFrame(position_data)
        if not df_position.empty:
            # Sum up the values by 'Symbol' and fill missing columns with 0
            df_position = df_position.groupby('Symbol').sum().reset_index()
            df_position = df_position[['Symbol', 'CE', 'PE', 'FUT', 'EQ']].fillna(0)
        else:
            df_position = pd.DataFrame(columns=['Symbol', 'CE', 'PE', 'FUT', 'EQ'])

        return df_position

    user_path = get_user_path(current_user.id)
    if not user_path:
        return redirect(url_for('index'))

    pro_client_value = group_data[current_user.id].get('pro_client', '')
    position_data = match_and_calculate(user_path, header_mapping, future_values, option_values, pro_client_value)

    return render_template('position1.html', position_data=position_data, group_name=current_user.id)



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('turnover'))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=8080, debug=True)
