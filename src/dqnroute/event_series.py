import pandas as pd

from typing import Callable, Dict, Optional, List

Aggregator = Callable[[Optional[float], float], float]

class EventSeries:
    def __init__(self, period: int, aggregators: Dict[str, Aggregator]):
        columns = ['time'] + list(aggregators.keys())

        self.records = pd.DataFrame(columns=columns)
        self.period = period
        self.aggregators = aggregators

    def _log(self, cur_period: int, value):
        avg_time = cur_period * self.period
        data_cols = self.records.columns[1:]

        try:
            data_vals = self.records.loc[cur_period, data_cols]
        except KeyError:
            data_vals = [None]*len(data_cols)

        new_data_vals = [self.aggregators[col](old_value, value)
                         for (col, old_value) in zip(data_cols, data_vals)]

        self.records.loc[cur_period] = [avg_time] + new_data_vals

    def logEvent(self, time, value):
        cur_period = int(time // self.period)
        self._log(cur_period, value)

    def logUniformRange(self, start, end, coeff):
        start_period = int(start // self.period)
        end_period = int(end // self.period)

        if start_period == end_period:
            self._log(start_period, (end - start) * coeff)
        else:
            start_gap = self.period - (start % self.period)
            end_gap = end % self.period

            self._log(start_period, coeff * start_gap)
            for period in range(start_period + 1, end_period):
                self._log(period, coeff * self.period)
            self._log(end_period, coeff * end_gap)

    def addAvg(self, avg_col='avg', sum_col='sum', count_col='count'):
        self.records[avg_col] = self.records[sum_col] / self.records[count_col]

    def getSeries(self):
        return self.records.sort_index().astype(float, copy=False)

    def reset(self):
        self.records = self.records.iloc[0:0]

    def load(self, csv_path):
        self.records = pd.read_csv(csv_path, index_col=False)

    def save(self, csv_path):
        self.getSeries().to_csv(csv_path, index=False)


class MultiEventSeries(EventSeries):
    def __init__(self, **series: Dict[str, EventSeries]):
        self.series = series

    def logEvent(self, tag: str, time, value):
        self.series[tag].logEvent(time, value)

    def logUniformRange(self, tag: str, start, end, coeff):
        self.series[tag].logUniformRange(start, end, coeff)

    def subSeries(self, tag: str):
        return self.series[tag]

    def allSubSeries(self):
        return self.series.items()

    def addAvg(self, avg_col='avg', sum_col='sum', count_col='count'):
        for s in self.series.values():
            s.addAvg(avg_col, sum_col, count_col)

    def getSeries(self):
        dfs = [s.getSeries().rename(columns=lambda c: tag + '_' + c)
               for (tag, s) in self.series.items()]
        return pd.concat(dfs, axis=1)

    def reset(self):
        for s in self.series.values():
            s.reset()

    def load(self, csv_path):
        dfs = split_dataframe(pd.read_csv(csv_path, index_col=False))
        for tag, df in dfs:
            self.series[tag].records = df


class ChangingValue(object):
    def __init__(self, data_series, init_val=0, avg=False):
        self.data = data_series
        self.cur_val = init_val
        self.avg = avg
        self.update_time = 0

    def update(self, time, val):
        assert time >= self.update_time, "time goes backwards?"
        d = time - self.update_time
        if d > 0 and self.cur_val != val:
            if self.avg:
                coeff = self.cur_val / d
            else:
                coeff = self.cur_val
            self.data.logUniformRange(self.update_time, time, coeff)
            self.cur_val = val
            self.update_time = time


def aggregator(f: Callable[[float, float], float], dv = None) -> Aggregator:
    """
    Make an aggregator from a simple function of two values
    """
    def _inner(a: Optional[float], b: float) -> float:
        if a is None:
            return dv if dv is not None else b
        return f(a, b)
    return _inner

def binary_func(name: str) -> Aggregator:
    """
    Helper for getting standard aggregator functions
    """
    if name == 'sum':
        return aggregator(lambda a, b: a + b)
    elif name == 'count':
        return aggregator(lambda a, _: a + 1, 1)
    elif name == 'max':
        return aggregator(max)
    elif name == 'min':
        return aggregator(min)
    else:
        raise Exception('Unknown aggregator function ' + name)

def event_series(period: int, aggr_names: List[str]) -> EventSeries:
    return EventSeries(period, {name: binary_func(name) for name in aggr_names})

def split_dataframe(all_records, preserved_cols=[]):
    tagged_cols = [col for col in all_records.columns if col not in preserved_cols]
    tagged = {}
    for col in tagged_cols:
        tag = col.split('_')[0]
        try:
            tagged[tag].append(col)
        except KeyError:
            tagged[tag] = [col]

    def _remove_tag(tag, col):
        if col.startswith(tag+'_'):
            return '_'.join(col.split('_')[1:])
        return col

    res = []
    for tag, cols in tagged.items():
        df = all_records.loc[:, cols + preserved_cols]
        df = df.rename(columns=lambda c: _remove_tag(tag, c))
        res.append((tag, df))
    return res
