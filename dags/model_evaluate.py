import os
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.metrics import r2_score, mean_squared_error

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

from util import (
    _FE, _GET_PREDICTION, _GET_QA, _LOG_METRIC, _LOG_PARAMETER, _SEND_RESULT,
    success_callback, failure_callback,
)


@dag(
    schedule=None,
    start_date=datetime(2024, 1, 1),
    tags=[],
    params={
        'model_id': 'multi_y_regressor',
        'prediction_path': '/predictions/multi_y_regressor/manual--2024-09-06T14-59-35-08-00',
        'date': "2024-01-01",
        'lot_id': "ATWLOT-010124-0852-553-001",
        'targets_name': [
            "al_squeeze_out_x",
            "al_squeeze_out_y",
            "outer_ball_size_x",
            "outer_ball_size_y",
            "ball_thickness",
            "loop_height",
            "outer_ball_shape",
            "inner_ball_shape",
        ]
    },
)
def model_evaluate():
    """DAG for evaluating model predictions."""

    @task(multiple_outputs=True, on_success_callback=success_callback, on_failure_callback=failure_callback)
    def data_collect():
        """Collect data for evaluation.

        Returns:
            dict: A dictionary containing ground_truth and prediction data.
        """
        try:
            context = get_current_context()
            params = context['params']
            prediction_path = params['prediction_path']
            date = params['date']
            lot_id = params['lot_id']
            targets_name = params['targets_name']

            print(f"Collecting prediction data from path: {prediction_path}")
            prediction, uid = _GET_PREDICTION(prediction_path, targets_name)

            print(f"Collecting ground truth data for date: {date}, lot_id: {lot_id}")
            ground_truth = _GET_QA(date, lot_id)
            g_uid = ground_truth['mapping_uid']
            ground_truth = ground_truth[targets_name]
            ground_truth = ground_truth.dropna()

            print("Checking if prediction and ground truth UIDs match")
            uids_match = set(uid) == set(g_uid)
            if not uids_match:
                print("Warning: The mapping_uids do not match between the prediction and ground_truth data.")

            return {
                'prediction': prediction,
                'ground_truth': ground_truth
            }

        except Exception as e:
            print(f"Error in data_collect: {str(e)}")
            raise e

    @task(on_success_callback=success_callback, on_failure_callback=failure_callback)
    def evaluate(ground_truth, prediction):
        """Evaluate the model predictions.

        Args:
            ground_truth (pd.DataFrame): The true ground_truth values.
            prediction (pd.DataFrame): The predicted values.

        Returns:
            dict: A dictionary containing evaluation metrics.
        """
        try:
            print("Calculating evaluation metrics")
            _r2_score = r2_score(ground_truth, prediction)
            _mse_score = mean_squared_error(ground_truth, prediction)
            errors = prediction.values - ground_truth.values
            _pos_max_err = errors.max()
            _neg_max_err = errors.min()

            metrics = {
                'r2_score': _r2_score,
                'mse_score': _mse_score,
                'pos_max_err': _pos_max_err,
                'neg_max_err': _neg_max_err,
            }
            print(f"Evaluation metrics: {metrics}")

            return metrics

        except Exception as e:
            print(f"Error in evaluate: {str(e)}")
            raise e

    @task(on_success_callback=success_callback, on_failure_callback=failure_callback)
    def collect_metric(metrics):
        """Log evaluation metrics to the server.

        Args:
            metrics (dict): The evaluation metrics.

        Returns:
            dict: The response from the server.
        """
        try:
            context = get_current_context()
            params = context['params']
            model_id = params['model_id']

            print(f"Logging metrics for model: {model_id}")
            response = _LOG_METRIC(model_id, metrics)

            return response

        except Exception as e:
            print(f"Error in collect_metric: {str(e)}")
            raise e

    @task(on_success_callback=success_callback, on_failure_callback=failure_callback)
    def send_result(metrics):
        """Send the evaluation metrics to the result server.

        Args:
            metrics (dict): The evaluation metrics.

        Returns:
            dict: The response from the server.
        """
        try:
            context = get_current_context()
            params = context['params']
            model_id = params['model_id']
            dag_params = context['dag_run']

            print(f"Sending results for model: {model_id}")
            response = _SEND_RESULT(model_id, dag_params, metrics)
            return response

        except Exception as e:
            print(f"Error in send_result: {str(e)}")
            raise e

    # Task: data collect
    data_collect_result = data_collect()
    ground_truth = data_collect_result['ground_truth']
    prediction = data_collect_result['prediction']
    # Task: evaluate
    metrics = evaluate(ground_truth, prediction)
    # Task: collect metric
    collect_metric_response = collect_metric(metrics)
    # Task: send result
    send_result_response = send_result(metrics)


# Define the DAG
evaluate_dag = model_evaluate()