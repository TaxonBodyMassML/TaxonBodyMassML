"""
data_split_visualtization.py
------------------------------
This program imports the BodyMass.csv data and
applies z-normalization to the mass_g variable.
It creates a log1p visualization of mass_g and a
yeo-johnson visualization of z-normalized mass.
It samples 10% of the data as test data and saves new test/train data.
"""

from pathlib import Path

import matplotlib

# import matplotlib.pyplot as plt
# import numpy as np
import pandas as pd

# import seaborn as sns
# from sklearn.preprocessing import PowerTransformer
# from ydata_profiling import ProfileReport

matplotlib.use("TkAgg")


# apply z normalization to the mass_g variable in the data
def z_normalization(df):
    """
    z_normalization()
    --------------------
    applies z-normalization to the mass_g variable.
    """
    # remove rows with missing data
    print("Number of missing values in each column:\n", df.isna().sum())
    df = df.dropna()

    # normalize mass data using z-normalization
    temp = df["mass_g"]
    df["normalized_mass"] = (temp - temp.mean()) / temp.std()
    print(df)

    return df


def main():
    """
    main()
    --------------------
    It creates a log1p visualization of mass_g and
    a yeo-johnson visualization of z-normalized mass.
    It samples 10% of the data as test data and saves new test/train data.
    """
    # read bodymass data into a pandas dataframe
    df = pd.read_csv("./data/BodyMass_curated.csv")

    # create a new variable which is the
    # mass_g variable with z-normalization applied
    # df = z_normalization(df)

    # ydata profiliing report is saved to my_report.html
    # profile = ProfileReport(df, title="Profiling Report")
    # profile.to_file(Path(__file__).parent / "my_report.html")

    # create log1p visualization for the mass_g variable
    # sns.histplot(np.log1p(df["mass_g"]), bins=50, kde=True)
    # plt.title("Log-Transformed mass_g (log1p)")
    # plt.ylabel("Count")
    # plt.xlabel("Mass (g)")
    # plt.show(block=True)

    # use yeo-johnson method to find a transformation that makes
    # visualizing normalized mass variable readable
    # pt = PowerTransformer(method="yeo-johnson")
    # normalized_mass = df["normalized_mass"].to_numpy()
    # transformed = pt.fit_transform(normalized_mass.reshape(-1, 1))
    # sns.histplot(transformed, bins=50, kde=True)
    # plt.title("Yeo-Johnson Transformed Mass Data")
    # plt.ylabel("Count")
    # plt.xlabel("Z-Normalized Mass")
    # plt.show(block=True)

    df = df.drop(["taxon", "source_mass", "n", "confidence", "subspecies", "form"], axis=1)
    print("Number of missing values in each column:\n", df.isna().sum())
    df = df.dropna()
    print(df)

    # test data is a random sample of 10% of the database
    test = df.sample(frac=0.1, replace=False)

    # train data is the remaining 90%
    train = df.drop(test.index)

    print(test)
    print(train)

    # save the train/test split to independent csv files
    test.to_csv("./data/test.csv", index=False)
    train.to_csv("./data/train.csv", index=False)


main()
