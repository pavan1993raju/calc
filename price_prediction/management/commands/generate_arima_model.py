from price_prediction.models import *
import pandas as pd
from glob import glob
import os
import math
import json
import datetime
import time
import numpy as np
from scipy import stats
import pandas as pd
import matplotlib.pyplot as plt
import statsmodels.api as sm
from statsmodels.graphics.api import qqplot
from scipy.optimize import brute
import statistics
from functools import partial
import os
import logging


from django.core.management import BaseCommand
from optparse import make_option
from django.core.management import call_command


#this comes from here: http://stackoverflow.com/questions/22770352/auto-arima-equivalent-for-python
def objective_function(data,order):
    return sm.tsa.ARIMA(data,order).fit().aic

def model_search(data):
    obj_func = partial(objective_function,data)
    #Back in graduate school professor Lecun said in class that ARIMA models typically only need a max parameter of 5, so I doubled it just in case.
    upper_bound_AR = 10
    upper_bound_I = 10
    upper_bound_MA = 10
    grid_not_found = True
    while grid_not_found:
        try:
            if upper_bound_AR < 0 or upper_bound_I < 0 or upper_bound_MA < 0:
                grid_not_found = False
            grid = (slice(1,upper_bound_AR,1),slice(1,upper_bound_I,1),slice(1,upper_bound_MA,1))
            return brute(obj_func, grid, finish=None)
        except Exception as e: #found here: http://stackoverflow.com/questions/4308182/getting-the-exception-value-in-python
            error_string = str(e)
            if "MA" in error_string:
                upper_bound_MA -= 1
            elif "AR" in error_string:
                upper_bound_AR -= 1
            else:
                upper_bound_I -= 1
    
                
                
    #assuming we don't ever hit a reasonable set of upper_bounds, it's pretty safe to assume this will work
    try:
        grid = (slice(1,2,1),slice(1,2,1),slice(1,2,1))
        return brute(obj_func, grid, finish=None)
    except: #however we don't always meet invertibility conditions
        #Here we explicitly test for a single MA or AR process being a better fit
        #If either has a lower (better) aic score we return that model order
        model_ar_one = sm.tsa.ARIMA(data,(1,0,0)).fit()
        model_ma_one = sm.tsa.ARIMA(data,(0,0,1)).fit()
        if model_ar_one.aic < model_ma_one.aic:
            return (1,0,0)
        else:
            return (0,0,1)


def date_to_datetime(time_string):
    return datetime.datetime.strptime(time_string, '%m/%d/%Y')

def ave_error(values,fitted_values):
    if (len(values) == len(fitted_values)) or (len(values) < len(fitted_values)):
        return sum([abs(values[ind] - fitted_values[ind]) for ind in range(len(values))])/len(values) 
    else:
        return sum([abs(values[ind] - fitted_values[ind]) for ind in range(len(fitted_values))])/len(values)
    
def check_for_extreme_values(sequence,sequence_to_check=None):
    mean = statistics.mean(sequence)
    stdev = statistics.stdev(sequence)
    if sequence_to_check != None:
        for val in sequence_to_check:
            if val >= mean + (stdev*2):
                sequence_to_check.remove(val)
            elif val <= mean - (stdev*2):
                sequence_to_check.remove(val)
        return sequence_to_check
    else:
        for val in sequence:
            if val >= mean + (stdev*2):
                sequence.remove(val)
            elif val <= mean - (stdev*2):
                sequence.remove(val)
        return sequence
        
def setting_y_axis_intercept(data,model):
    try:
        #if we are using the original data
        data = list(data["Price"])
    except:
        #if we are using the deseasonalized data
        data = list(data)
    fittedvalues = list(model.fittedvalues)
    avg = statistics.mean(data)
    median = statistics.median(data)
    possible_fitted_values = []

    possible_fitted_values.append([elem + avg for elem in fittedvalues])
    possible_fitted_values.append([elem + data[0] for elem in fittedvalues])
    possible_fitted_values.append([elem + median for elem in fittedvalues])
    possible_fitted_values.append(fittedvalues)
    min_error = 1000000
    best_fitted_values = 0
    for ind,f_values in enumerate(possible_fitted_values):
        avg_error = ave_error(data,f_values)
        if avg_error < min_error:
            min_error = avg_error 
            best_fitted_values = ind
    print("minimum error:",min_error)
    return possible_fitted_values[best_fitted_values]

def check_for_extreme_values(sequence,sequence_to_check=None):
    mean = statistics.mean(sequence)
    stdev = statistics.stdev(sequence)
    if sequence_to_check != None:
        for val in sequence_to_check:
            if val >= mean + (stdev*2):
                sequence_to_check.remove(val)
            elif val <= mean - (stdev*2):
                sequence_to_check.remove(val)
        return sequence_to_check
    else:
        for val in sequence:
            if val >= mean + (stdev*2):
                sequence.remove(val)
            elif val <= mean - (stdev*2):
                sequence.remove(val)
        return sequence
        
def trend_predict(data):
    #seasonal decompose 
    if len(data) > 52:
        s = sm.tsa.seasonal_decompose(data["Price"],freq=52)
    elif len(data) > 12:
        s = sm.tsa.seasonal_decompose(data["Price"], freq=12)
    else:
        return None
    #clearing out NaNs
    new_data = s.trend.fillna(0)
    new_data = new_data.iloc[new_data.nonzero()[0]]
    model_order = list(model_search(data))
    model_order = tuple([int(elem) for elem in model_order])
    model = sm.tsa.ARIMA(new_data,model_order).fit()
    model.fittedvalues = setting_y_axis_intercept(new_data,model)
    return model,new_data

def is_nan(obj):
    if type(obj) == type(float()):
        return math.isnan(obj)
    else:
        return False
    
def money_to_float(string):
    """
    hourly wages have dollar signs and use commas, 
    this method removes those things, so we can treat stuff as floats
    """
    if type(string) == type(str()):
        string = string.replace("$","").replace(",","")
        return float(string)
    else:
        return string

def load_data():
    """
    this loads all the csv's into memory and then returns them.
    Note that only versioned csv's are returned, because the one without a version number
    is also the highest numbered CSV.  This avoids *some* double counting.
    """
    #loading the datasets into memory
    os.chdir("data")
    data_sets = ["hourly_prices_v1.csv","hourly_prices_v2.csv","hourly_prices_v3.csv","hourly_prices_v4.csv"]
    dfs = [pd.read_csv(data_set) for data_set in data_sets]
    os.chdir("..")
    return dfs


class Command(BaseCommand):

    default_filename = 'contracts/docs/hourly_prices.csv'

    option_list = BaseCommand.option_list + (
        make_option(
            '-f', '--filename',
            default=default_filename,
            help='input filename (.csv, default {})'.format(default_filename)
        ),
    )

    def handle(self, *args, **options):
        labor_categories = [elem.labor_key for elem in LaborCategoryLookUp.objects.all()]

        for labor_category in labor_categories:
            labor_objects = LaborCategoryLookUp.objects.filter(labor_key=labor_category)
            df = pd.DataFrame()
            for labor_object in labor_objects:
                df = df.append({"Date":labor_object.start_date,"Price":float(labor_object.labor_value)},ignore_index=True)
            #sanity checking this is a datetime
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")
            df.sort_index(inplace=True)
            model,new_data = trend_predict(df)
            predicted_data = pd.DataFrame()
            for ind in range(len(model.fittedvalues)):
                predicted_data = predicted_data.append({"date":model.data.dates[ind],"price":model.fittedvalues[ind]},ignore_index=True)
            predicted_data["date"] = pd.to_datetime(predicted_data["date"])
            predicted_data = predicted_data.set_index("date")
            predicted_data.sort_index(inplace=True)
            plt.plot(df)
            plt.plot(predicted_data)
            plt.show()

            #We are using timestamps for the index
            for ind in range(len(predicted_data.index)):
                try:
                    fitted_values_by_category = FittedValuesByCategory(labor_key=labor_category,fittedvalue=predicted_data["price"][ind],start_date=predicted_data.index[ind])
                    fitted_values_by_category.save()
                except:
                    import code
                    code.interact(local=locals())

# results = sm.tsa.ARIMA(dta, (3,1,0)).fit()
# results.save
# sm.load()


