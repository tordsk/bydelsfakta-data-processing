#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
import json, boto3, re

# Add missing ages
tempdf = pd.DataFrame(data=np.zeros(120))


def handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        p = re.compile(r'^(\w+)/(\w+)/(\w+)/(\w+)/(\d+)/([^/]+)[.](csv?)$', flags=re.IGNORECASE)
        m = p.match(key)
        if not m:
            raise ValueError('S3 key does not satisfy pattern')

        (condition, confidentiality, dataset, version, edition, prefix, suffix) = m.groups()

        out_key = 'processed/{confidentiality}/{dataset}/{version}/{edition}/{distribution}'.format(
            confidentiality=confidentiality,
            dataset="aldersbefolkning_bydel",
            version=version,
            edition=edition,
            distribution=prefix + '.' + "json")

        source = pd.read_csv('s3://{bucket}/{key}'.format(bucket=bucket, key=key),
                             sep=";",
                             encoding='utf8')

        df = init_dataframe(source)

        jsonlist = [create_specific_bydel(district, transform(df)) for district in districts]
        s3 = boto3.resource('s3', region_name='eu-west-1')
        s3.Object(bucket, out_key).put(Body=json.dumps(jsonlist), ContentType='application/json')


def transform(df):
    df = df.append(bydel_avg(df))
    df = df.append(bydel_max(df))

    df['Mann'] = df['Mann'].fillna(0)
    df['Kvinne'] = df['Kvinne'].fillna(0)
    df['value'] = df['Mann'] + df['Kvinne']

    return (df.groupby(['aargang', 'bydel2', 'geography', 'totalRow', 'avgRow'], as_index=True)
            .apply(lambda x: toDict(x))
            .apply(lambda x: processDict(x))
            .reset_index()
            .rename(columns={0: 'values'})
            .to_dict(orient='records'))


def bydel_avg(dataframe):
    averages_df = dataframe.groupby(['aargang', 'bydel2', 'alderu']
                                    ).apply(lambda x: x.sum())
    averages_df['geography'] = 'total'
    averages_df.set_index('geography', append=True,
                          inplace=True)
    averages_df = averages_df.reset_index()
    averages_df['geography'] = averages_df['bydel2']
    averages_df.set_index(['aargang', 'bydel2', 'geography',
                           'alderu'], inplace=True)
    averages_df['avgRow'] = True
    averages_df['totalRow'] = False
    return averages_df


def bydel_max(dataframe):
    max_df = dataframe.groupby(['aargang', 'alderu']).apply(lambda x: x.sum())
    max_df['geography'] = 'Oslo i alt'
    max_df['bydel2'] = 'Oslo'
    max_df.set_index('geography', append=True, inplace=True)
    max_df = max_df.reset_index()
    max_df.set_index(
        ['aargang', 'bydel2', 'geography', 'alderu'], inplace=True)
    max_df['totalRow'] = True
    max_df['avgRow'] = False
    return max_df


def init_dataframe(df):
    df = df.drop(columns="Obs")
    df = df[df['aargang'] == df['aargang'].max()]
    df = df.rename(columns={'delbydel001ny': 'geography'})
    df = df[df['geography'] != 'Uten registrert adresse']

    df['alderu'] = df['alderu'].str.replace(
        ' år', '').apply(lambda x: pd.to_numeric(x))

    df = df.pivot_table(index=['aargang', 'bydel2', 'geography',
                               'alderu'], columns=['kjoenn'], values="antall")

    df['avgRow'] = False
    df['totalRow'] = False
    return df


def toDict(row):
    # print(row)
    row = row.reset_index(level=['alderu'])
    row['ratio'] = row['value'] / row['value'].sum()
    # row = row.round({'ratio': 4})
    return row[['Mann', 'Kvinne', 'value', 'ratio', 'alderu']].to_dict('r')


def processDict(row):
    newRow = []
    idx = 0
    count = 0
    while count < 120:
        try:
            if row[idx]['alderu'] == count:
                newRow.append(row[idx])
                idx += 1
                count += 1
            else:
                if newRow[idx]['alderu'] == idx:
                    newRow.append({'Mann': 0.0, 'Kvinne': 0.0, 'alderu': count, 'value': 0, 'ratio': 0})
                    count += 1
        except:
            newRow.append({'Mann': 0.0, 'Kvinne': 0.0,
                           'alderu': count, 'value': 0, 'ratio': 0})
            count += 1

    return newRow


def create_specific_bydel(bydel, df):
    final = {
        'meta': {
            'scope': 'bydel',
            'heading': 'Størrelsen av alderssegmenter i Bydel ' + bydel + ' (01.01.2018)',
            'help': 'Dette er en beskrivelse for hvordan dataene leses',
            'publishedDate': '2019-06-01',
            'dataSource': {
                'url': 'http://ssb.no/data/1234124/',
                'label': 'Statistisk sentralbyrå'
            },
            'files': [
                {
                    'url': 'http://data.oslo.kommune.no/data/1234123/data.xls',
                    'type': 'Excel'
                },
                {
                    'url': 'http://data.oslo.kommune.no/data/1234123/data.csv',
                    'type': 'csv'
                }
            ]
        },
        'data': []
    }

    for idx in range(len(df)):
        if df[idx]['bydel2'] == bydel:
            final['data'].append(df[idx])
        if df[idx]['bydel2'] == 'Oslo':
            final['data'].append(df[idx])
    return final


def merge_df(x):
    new_df = x.join(tempdf, how="right", on="alderu")
    new_df = new_df.reset_index()
    new_df = new_df.drop(
        columns=['aargang', 'bydel2', 'geography', 0, 'index']).set_index('alderu')
    return new_df


districts = [
    "Alna",
    "Bjerke",
    "Frogner",
    "Gamle Oslo",
    "Grorud",
    "Grünerløkka",
    "Nordre Aker",
    "Nordstrand",
    "Sagene",
    "St. Hanshaugen",
    "Stovner",
    "Søndre Nordstrand",
    "Ullern",
    "Vestre Aker",
    "Østensjø"
]
