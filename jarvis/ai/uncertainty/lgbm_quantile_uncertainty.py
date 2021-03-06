"""
Code to predict properties and their uncertainty.

ML model used: lgbm
"""

from monty.serialization import loadfn, MontyDecoder
import numpy as np

# import matplotlib as plt

from sklearn.model_selection import (
    train_test_split,
    RandomizedSearchCV,
)
import scipy as sp
from sklearn.feature_selection import (
    VarianceThreshold,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import pickle

# Modeling
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
import lightgbm as lgb

# ---------------------------------------------------------------------


def quantile_regr_predint(
    x, y, jid, cv, n_jobs, n_iter, random_state, scoring, prop, info
):
    """
    Perform Quantile regression and determine prediction intervals.

    LOWER_ALPHA = 0.16
    Mid model uses ls as loss function, not quantile, to
        optimize for the mean, not the median
    UPPER_ALPHA = 0.84
    This choice of LOWER_ALPHA, UPPER_ALPHA gives a prediction
    interval ideally equal to 0.68, i.e. 1 standard deviation.
    However, the number of in-bound prediction must be computed
    for the specific fitted models, and that gives the true meaning
    of the uncertainties computed here.
    """
    # STEP-2: Splitting the data
    # ***************************
    # 90-10% split for train test

    X_train, X_test, y_train, y_test, jid_train, jid_test = train_test_split(
        x, y, jid, random_state=1, test_size=0.1
    )
    # print ('lenx len y',len(x[0]),len(y))

    # STEP-3: Use a specific ML model
    # ********************************

    # Set lower and upper quantile
    # StanDev
    LOWER_ALPHA = 0.16
    # MID_ALPHA = 0.50
    UPPER_ALPHA = 0.84

    # LOWER Model
    # ===========
    scaler = StandardScaler().fit(X_train)
    scaler.transform(X_train)
    scaler.transform(X_test)

    objective = "quantile"
    alpha = LOWER_ALPHA
    print("Prima di lgbm for LOWER model")
    lower_model = get_lgbm(
        X_train,
        X_test,
        y_train,
        y_test,
        cv,
        n_jobs,
        scoring,
        n_iter,
        objective,
        alpha,
        random_state,
    )
    print("Dopo lgbm for LOWER model")
    name = str(prop) + str("_lower")
    filename = str("pickle2-") + str(name) + str(".pk")
    pickle.dump(lower_model, open(filename, "wb"))

    # MID Model
    # =========
    scaler = StandardScaler().fit(X_train)
    scaler.transform(X_train)
    scaler.transform(X_test)

    # mid_model.fit(X_train, y_train)
    objective = "regression"
    alpha = 0.9
    print("Prima di lgbm for MID model")
    mid_model = get_lgbm(
        X_train,
        X_test,
        y_train,
        y_test,
        cv,
        n_jobs,
        scoring,
        n_iter,
        objective,
        alpha,
        random_state,
    )
    print("Dopo lgbm for MID model")
    name = str(prop) + str("_mid")
    filename = str("pickle2-") + str(name) + str(".pk")
    pickle.dump(mid_model, open(filename, "wb"))

    # UPPER Model
    # ===========
    scaler = StandardScaler().fit(X_train)
    scaler.transform(X_train)
    scaler.transform(X_test)

    # upper_model.fit(X_train, y_train)
    objective = "quantile"
    alpha = UPPER_ALPHA
    print("Prima di lgbm for UPPER model")
    upper_model = get_lgbm(
        X_train,
        X_test,
        y_train,
        y_test,
        cv,
        n_jobs,
        scoring,
        n_iter,
        objective,
        alpha,
        random_state,
    )
    print("Dopo lgbm for UPPER model")
    name = str(prop) + str("_upper")
    filename = str("pickle2-") + str(name) + str(".pk")
    pickle.dump(upper_model, open(filename, "wb"))

    # PREDICTIONS and UQ
    lower = lower_model.predict(X_test)
    mid = mid_model.predict(X_test)
    upper = upper_model.predict(X_test)
    actual = y_test

    print("Model       mae     rmse")
    reg_sc = regr_scores(y_test, lower)
    info["MAE_Lower"] = reg_sc["mae"]
    print("Lower:", round(reg_sc["mae"], 3), round(reg_sc["rmse"], 3))
    reg_sc = regr_scores(y_test, mid)
    info["MAE_Mid"] = reg_sc["mae"]
    print("Mid:", round(reg_sc["mae"], 3), round(reg_sc["rmse"], 3))
    reg_sc = regr_scores(y_test, upper)
    info["MAE_Upper"] = reg_sc["mae"]
    print("Upper:", round(reg_sc["mae"], 3), round(reg_sc["rmse"], 3))

    """
 Calculate the absolute error associated with prediction intervals
 """
    # in_bounds = actual.between(left=lower, right=upper)

    fout1 = open("Intervals.dat", "w")
    fout2 = open("Intervals1.dat", "w")
    line0 = "#    Jid      Observed       pred_Lower"
    line1 = "       pred_Mid        pred_Upper\n"
    line = line0 + line1
    fout1.write(line)
    line0 = "#    Jid      Observed       pred_Lower    AbsErr(Lower)"
    line1 = "     pred_Mid    AbsErr(Mid)     pred_Upper"
    line2 = "     AbsErr(Upper)    AbsErrInterval    Pred_inBounds\n"
    line = line0 + line1 + line2
    fout2.write(line)
    sum = 0.0
    count = 0
    MAE_err = 0.0
    for ii in range(len(actual)):
        true = float(actual[ii])
        llow = float(lower[ii])
        mmid = float(mid[ii])
        uupper = float(upper[ii])
        err = abs((uupper - llow) * 0.5)
        diff = true - mmid
        real_err = abs(diff)
        err_err = abs(real_err - err)
        MAE_err = MAE_err + err_err
        if abs(diff) < err:
            count = count + 1
            in_bounds = "True"
        else:
            in_bounds = "False"
        absolute_error_lower = abs(lower[ii] - actual[ii])
        absolute_error_mid = abs(mid[ii] - actual[ii])
        absolute_error_upper = abs(upper[ii] - actual[ii])
        absolute_error_interval = (
            absolute_error_lower + absolute_error_upper
        ) / 2.0

        line = (
            str(ii)
            + " "
            + jid[ii]
            + " "
            + str(actual[ii])
            + " "
            + str(lower[ii])
            + " "
            + str(mid[ii])
            + " "
            + str(upper[ii])
            + "\n"
        )
        sum = sum + float(absolute_error_interval)
        line2 = (
            str(ii)
            + " "
            + jid[ii]
            + " "
            + str(actual[ii])
            + " "
            + str(lower[ii])
            + " "
            + str(absolute_error_lower)
            + " "
            + str(mid[ii])
            + " "
            + str(absolute_error_mid)
            + " "
            + str(upper[ii])
            + " "
            + str(absolute_error_upper)
            + " "
            + str(absolute_error_interval)
            + " "
            + str(in_bounds)
            + "\n"
        )
        fout1.write(line)
        fout2.write(line2)
    print("")
    print("Number of test materials= " + str(len(actual)))
    print(
        "Percentage of in-bound results= "
        + str((float(count) / (len(actual))) * 100)
        + "%"
    )
    print(" ")
    MAE_error = float(MAE_err) / (len(actual))
    print("MAE predicted error (err=0.5*(High-Low))= " + str(MAE_error))
    info["MAE_Error"] = MAE_error


def get_number_formula_unit(s=""):
    """Determine the number of unit cells."""
    orig_formula = s.composition.as_dict()
    prim_formula = s.get_primitive_structure().composition.as_dict()
    num_unit = float(orig_formula.values()[0]) / float(
        prim_formula.values()[0]
    )
    return num_unit


def isfloat(value):
    """Determine if a value is a float."""
    try:
        float(value)
        return True
    except ValueError:
        return False
        pass


def jdata(prop=""):
    """Read of database for chosen physical quantity."""
    # d3=loadfn('/rk2/ftavazza/ML/NEW/Quantile/New_quantities/jml_3d-4-26-2020.json',cls=MontyDecoder)
    d3 = loadfn(
        "/users/ftavazza/ML/ruth_New/jml_3d-4-26-2020.json", cls=MontyDecoder
    )
    # limits={'form_enp':[-5,5],'exfoliation_en':[0,1000],'el_mass_x':[0,100],'el_mass_y':[0,100],'el_mass_z':[0,100],'hl_mass_x':[0,100],'hl_mass_y':[0,100],'hl_mass_z':[0,100],'magmom':[0,10],'fin_en':[0,0],'op_gap':[-1,10],'kv':[-1,500],'gv':[-15,510],'encut':[500,3000],'kp_leng':[40,200],'epsx':[0,50],'epsy':[0,50],'epsz':[0,50],'mepsx':[0,50],'mepsy':[0,50],'mepsz':[0,50],'mbj_gap':[-1,10]}

    limits = {
        "formation_energy_peratom": [-5, 5],
        "optb88vdw_bandgap": [0, 10],
        "mbj_bandgap": [0, 10],
        "bulk_modulus_kv": [0, 250],
        "shear_modulus_gv": [0, 250],
        "epsx": [0, 60],
        "epsy": [0, 60],
        "epsz": [0, 60],
        "mepsx": [0, 60],
        "mepsy": [0, 60],
        "mepsz": [0, 60],
        "n-Seebeck": [-600, 10],
        "n-powerfact": [0, 5000],
        "p-Seebeck": [-10, 600],
        "p-powerfact": [0, 5000],
        "slme": [0, 40],
        "spillage": [0, 4],
        "encut": [0, 2000],
        "kpoint_length_unit": [0, 200],
        "dfpt_piezo_max_dielectric": [0, 100],
        "dfpt_piezo_max_dij": [0, 3000],
        "dfpt_piezo_max_eij": [0, 10],
        "ehull": [0, 1],
        "electron_avg_effective_masses_300K": [0, 3],
        "hole_avg_effective_masses_300K": [0, 3],
        "exfoliation_energy": [0, 1000],
        "magmom_oszicar": [0, 10],
        "max_ir_mode": [0, 4000],
        "total_energy_per_atom": [-10, 3],
    }
    X = []
    Y = []
    jid = []
    for ii, i in enumerate(d3):
        # if ii<100:
        y = i[prop]
        if isfloat(y):
            y = float(y)
            if y >= limits[prop][0] and y <= limits[prop][1]:
                x = i["desc"]  # get_comp_descp(i['final_str'])
                # if len(x)==1557 and
                # any(np.isnan(x) for x in x.flatten())==False:
                if (
                    len(x) == 1557
                ):  # and any(np.isnan(x) for x in x.flatten())==False:
                    if "eps" in prop:
                        y = np.sqrt(float(y))
                    if "mag" in prop:
                        num = get_number_formula_unit(i["strt"])
                        y = float(abs(y)) / float(num)

                    X.append(x)
                    Y.append(y)
                    jid.append(i["jid"])
    print("max,min", max(Y), min(Y))
    print("Prop=", prop, len(X), len(Y))
    X = np.array(X).astype(np.float64)
    Y = np.array(Y).astype(np.float64)
    return X, Y, jid


# def regr_scores(pred,test):
def regr_scores(test, pred):
    """
    Compute generic regresion scores.

    Args:
        pred: predicted values
        test: held data for testing
    Returns:
         info: with metrics.
    """
    rmse = np.sqrt(mean_squared_error(test, pred))
    r2 = r2_score(test, pred)
    mae = mean_absolute_error(test, pred)
    info = {}
    info["mae"] = mae
    info["rmse"] = rmse
    info["r2"] = r2
    info["test"] = test
    info["pred"] = pred
    return info


def get_lgbm(
    train_x,
    val_x,
    train_y,
    val_y,
    cv,
    n_jobs,
    scoring,
    n_iter,
    objective,
    alpha,
    random_state,
):
    """
    Train a lightgbm model.

    Args:
        train_x: samples used for trainiing
        val_x: validation set
        train_y: train targets
        val_y: validation targets
        cv: # of cross-validations
        n_jobs: for making the job parallel
        scoring: scoring function to use such as MAE
    Returns:
           Best estimator.
    """
    # def get_lgbm(train_x, val_x, train_y,val_y,cv,n_jobs,scoring,n_iter):
    # Get converged boosting iterations with high learning rate,
    # MAE as the convergence crietria
    lgbm = lgb.LGBMRegressor(
        n_estimators=500,
        learning_rate=0.1,
        max_depth=5,
        num_leaves=100,
        objective=objective,
        # min_data_in_leaf=2,
        n_jobs=-1,
        alpha=alpha,
        random_state=random_state,
        verbose=-1,
    )

    lgbm.fit(
        train_x,
        train_y,
        eval_set=[(val_x, val_y)],
        eval_metric="mae",
        # eval_metric='l1',
        early_stopping_rounds=10,
    )
    num_iteration = lgbm.best_iteration_
    print("num_iteration", num_iteration)
    print("in randomsearch cv")
    # Generally thousands of randomized search for optimal parameters
    # learning rate and num_leaves are very important
    param_dist = {
        # 'boosting_type': [ 'dart'],
        # 'boosting_type': ['gbdt', 'dart', 'rf'],
        # 'num_leaves': sp.stats.randint(2, 1001),
        # 'subsample_for_bin': sp.stats.randint(10, 1001),
        # 'min_split_gain': sp.stats.uniform(0, 5.0),
        # 'min_child_weight': sp.stats.uniform(1e-6, 1e-2),
        # 'reg_alpha': sp.stats.uniform(0, 1e-2),
        # 'reg_lambda': sp.stats.uniform(0, 1e-2),
        # 'tree_learner': ['data', 'feature', 'serial', 'voting' ],
        # 'application': ['regression_l1', 'regression_l2', 'regression'],
        # 'bagging_freq': sp.stats.randint(1, 11),
        # 'bagging_fraction': sp.stats.uniform(.1, 0.9),
        # 'feature_fraction': sp.stats.uniform(.1, 0.9),
        # 'learning_rate': sp.stats.uniform(1e-3, 0.9),
        # 'est__num_leaves': [2,8,16],
        # 'est__min_data_in_leaf': [1,2,4],
        # 'est__learning_rate': [0.005,0.01,0.1],
        # 'est__max_depth': [1,3,5], #sp.stats.randint(1, 501),
        # 'est__n_estimators': [num_iteration,2*num_iteration,5*num_iteration],
        # sp.stats.randint(100, 20001),
        # 'gpu_use_dp': [True, False],
        "est__min_data_in_leaf": sp.stats.randint(5, 20),
        "est__n_estimators": sp.stats.randint(500, 2000),
        "est__num_leaves": sp.stats.randint(100, 500),
        "est__max_depth": sp.stats.randint(8, 20),
        "est__learning_rate": sp.stats.uniform(5e-3, 0.5),
    }
    lgbm = lgb.LGBMRegressor(
        objective=objective,
        # device='gpu',
        # n_estimators=num_iteration,
        n_jobs=n_jobs,
        alpha=alpha,
        verbose=-1,
    )
    pipe = Pipeline(
        [
            ("stdscal", StandardScaler()),
            ("vart", VarianceThreshold(1e-4)),
            ("est", lgbm),
        ]
    )

    # n_iter=10
    # Increase n_iter
    rscv = RandomizedSearchCV(
        estimator=pipe,
        param_distributions=param_dist,
        cv=cv,
        scoring=scoring,
        n_iter=n_iter,
        n_jobs=n_jobs,
        verbose=-1,
        random_state=random_state,
        refit=True,
    )
    model = rscv.fit(train_x, train_y)
    print("Best Score: ", model.best_score_)
    print("Best Params: ", model.best_params_)
    print("Best Estimator: ", model.best_estimator_)
    # return model.best_estimator_
    return model


# Main-function
def test_run(
    version="version_1",
    scoring="neg_mean_absolute_error",
    cv=5,
    n_jobs=1,
    prop="op_gap",
    do_cv=False,
):
    """
    Train-test split etc.

    Generic run function to train-test split,
    find optimum number of boosting operations,
    the hyperparameter optimization,
    learning curves, n-fold cross-validations,
    saving parameters and results


    Args:
        version: user defined name
        scoring: evaluation metric
        cv: # of cross-validation
        n_jobs: for running in parallel
        prop: property to train
        do_cv: whether to perform cross validation

    """
    # STEP-1: Getting Data
    # ********************
    property = "exfoliation_energy"

    x, y, jid = jdata(property)

    x = x[0:100]
    y = y[0:100]
    jid = jid[0:100]

    # STEP-2: Quantile regression to make predictions and determine
    #         prediction intervals for predicted data
    # **************************************************************

    # Search parameters
    scoring = "neg_mean_absolute_error"
    cv = 2
    n_jobs = -1
    # n_iter = how many parameter combination to try in the search
    n_iter = 10
    random_state = 508842607

    info = {}
    quantile_regr_predint(
        x, y, jid, cv, n_jobs, n_iter, random_state, scoring, property, info
    )


# run(prop="exfoliation_energy")
