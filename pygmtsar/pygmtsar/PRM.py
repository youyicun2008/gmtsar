# ----------------------------------------------------------------------------
# PyGMTSAR
# 
# This file is part of the PyGMTSAR project: https://github.com/mobigroup/gmtsar
# 
# Copyright (c) 2021, Alexey Pechnikov
# 
# Licensed under the BSD 3-Clause License (see LICENSE for details)
# ----------------------------------------------------------------------------
from .datagrid import datagrid
from .PRM_gmtsar import PRM_gmtsar

class PRM(datagrid, PRM_gmtsar):

    # my replacement function for GMT based robust 2D trend coefficient calculations:
    # gmt trend2d r.xyz -Fxyzmw -N1r -V
    # gmt trend2d r.xyz -Fxyzmw -N2r -V
    # gmt trend2d r.xyz -Fxyzmw -N3r -V
    # https://github.com/GenericMappingTools/gmt/blob/master/src/trend2d.c#L719-L744
    # 3 model parameters
    # rank = 3 => nu = size-3
    @staticmethod
    def robust_trend2d(data, rank):
        """
        Perform robust linear regression to estimate the trend in 2D data.

        Parameters
        ----------
        data : numpy.ndarray
            Array containing the input data. The shape of the array should be (N, 3), where N is the number of data points.
            The first column represents the x-coordinates, the second column represents the y-coordinates (if rank is 3),
            and the third column represents the z-values.
        rank : int
            Number of model parameters to fit. Should be 1, 2, or 3. If rank is 1, the function fits a constant trend.
            If rank is 2, it fits a linear trend. If rank is 3, it fits a planar trend.

        Returns
        -------
        numpy.ndarray
            Array containing the estimated trend coefficients. The length of the array depends on the specified rank.
            For rank 1, the array will contain a single value (intercept).
            For rank 2, the array will contain two values (intercept and slope).
            For rank 3, the array will contain three values (intercept, slope_x, slope_y).

        Raises
        ------
        Exception
            If the specified rank is not 1, 2, or 3.

        Notes
        -----
        The function performs robust linear regression using the M-estimator technique. It iteratively fits a linear model
        and updates the weights based on the residuals until convergence. The weights are adjusted using Tukey's bisquare
        weights to downweight outliers.

        References
        ----------
        - Rousseeuw, P. J. (1984). Least median of squares regression. Journal of the American statistical Association, 79(388), 871-880.

        - Huber, P. J. (1973). Robust regression: asymptotics, conjectures and Monte Carlo. The Annals of Statistics, 1(5), 799-821.
        """
        import numpy as np
        from sklearn.linear_model import LinearRegression
        # scale factor for normally distributed data is 1.4826
        # https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.median_abs_deviation.html
        MAD_NORMALIZE = 1.4826
        # significance value
        sig_threshold = 0.51

        if rank not in [1,2,3]:
            raise Exception('Number of model parameters "rank" should be 1, 2, or 3')

        #see gmt_stat.c
        def gmtstat_f_q (chisq1, nu1, chisq2, nu2):
            import scipy.special as sc

            if chisq1 == 0.0:
                return 1
            if chisq2 == 0.0:
                return 0
            return sc.betainc(0.5*nu2, 0.5*nu1, chisq2/(chisq2+chisq1))

        if rank in [2,3]:
            x = data[:,0]
            x = np.interp(x, (x.min(), x.max()), (-1, +1))
        if rank == 3:
            y = data[:,1]
            y = np.interp(y, (y.min(), y.max()), (-1, +1))
        z = data[:,2]
        w = np.ones(z.shape)

        if rank == 1:
            xy = np.expand_dims(np.zeros(z.shape),1)
        elif rank == 2:
            xy = np.expand_dims(x,1)
        elif rank == 3:
            xy = np.stack([x,y]).transpose()

        # create linear regression object
        mlr = LinearRegression()

        chisqs = []
        coeffs = []
        while True:
            # fit linear regression
            mlr.fit(xy, z, sample_weight=w)

            r = np.abs(z - mlr.predict(xy))
            chisq = np.sum((r**2*w))/(z.size-3)    
            chisqs.append(chisq)
            k = 1.5 * MAD_NORMALIZE * np.median(r)
            w = np.where(r <= k, 1, (2*k/r) - (k * k/(r**2)))
            sig = 1 if len(chisqs)==1 else gmtstat_f_q(chisqs[-1], z.size-3, chisqs[-2], z.size-3)
            # Go back to previous model only if previous chisq < current chisq
            if len(chisqs)==1 or chisqs[-2] > chisqs[-1]:
                coeffs = [mlr.intercept_, *mlr.coef_]

            #print ('chisq', chisq, 'significant', sig)
            if sig < sig_threshold:
                break

        # get the slope and intercept of the line best fit
        return (coeffs[:rank])

#     # standalone function is compatible but it is too slow while it should not be a problem
#     @staticmethod
#     def robust_trend2d(data, rank):
#         import numpy as np
#         import statsmodels.api as sm
# 
#         if rank not in [1, 2, 3]:
#             raise Exception('Number of model parameters "rank" should be 1, 2, or 3')
# 
#         if rank in [2, 3]:
#             x = data[:, 0]
#             x = np.interp(x, (x.min(), x.max()), (-1, +1))
#         if rank == 3:
#             y = data[:, 1]
#             y = np.interp(y, (y.min(), y.max()), (-1, +1))
#         z = data[:, 2]
# 
#         if rank == 1:
#             X = sm.add_constant(np.ones(z.shape))
#         elif rank == 2:
#             X = sm.add_constant(x)
#         elif rank == 3:
#             X = sm.add_constant(np.column_stack((x, y)))
# 
#         # Hampel weighting function looks the most accurate for noisy data
#         rlm_model = sm.RLM(z, X, M=sm.robust.norms.Hampel())
#         rlm_results = rlm_model.fit()
# 
#         return rlm_results.params[:rank]

#     # calculate MSE (optional)
#     @staticmethod
#     def robust_trend2d_mse(data, coeffs, rank):
#         import numpy as np
# 
#         x = data[:, 0]
#         y = data[:, 1]
#         z_actual = data[:, 2]
# 
#         if rank == 1:
#             z_predicted = coeffs[0]
#         elif rank == 2:
#             z_predicted = coeffs[0] + coeffs[1] * x
#         elif rank == 3:
#             z_predicted = coeffs[0] + coeffs[1] * x + coeffs[2] * y
# 
#         mse = np.mean((z_actual - z_predicted) ** 2)
#         return mse

    @staticmethod
    def from_list(prm_list):
        """
        Convert a list of parameter and value pairs to a PRM object.

        Parameters
        ----------
        prm_list : list
            A list of PRM strings.

        Returns
        -------
        PRM
            A PRM object.
        """
        from io import StringIO
        prm = StringIO('\n'.join(prm_list))
        return PRM._from_io(prm)

    @staticmethod
    def from_str(prm_string):
        """
        Convert a string of parameter and value pairs to a PRM object.

        Parameters
        ----------
        prm_string : str
            A PRM string.

        Returns
        -------
        PRM
            A PRM object.
        """
        from io import StringIO
        prm = StringIO(prm_string)
        return PRM._from_io(prm)

    @staticmethod
    def from_file(prm_filename):
        """
        Convert a PRM file of parameter and value pairs to a PRM object.

        Parameters
        ----------
        prm_filename : str
            The filename of the PRM file.

        Returns
        -------
        PRM
            A PRM object.
        """
        #data = json.loads(document)
        prm = PRM._from_io(prm_filename)
        prm.filename = prm_filename
        return prm

    @staticmethod
    def _from_io(prm):
        """
        Read parameter and value pairs from IO stream to a PRM object.

        Parameters
        ----------
        prm : IO stream
            The IO stream.

        Returns
        -------
        PRM
            A PRM object.
        """
        import pandas as pd
        return PRM(pd.read_csv(prm, sep='\s+=\s+', header=None, names=['name', 'value'], engine='python').set_index('name')\
                    .applymap(lambda val : pd.to_numeric(val,errors='ignore')))

    def __init__(self, prm=None):
        """
        Initialize a PRM object.

        Parameters
        ----------
        prm : PRM or pd.DataFrame, optional
            The PRM object or DataFrame to initialize from. Default is None.

        Returns
        -------
        None
        """
        import pandas as pd
        #print ('__init__')
        if prm is None:
            _prm = pd.DataFrame(None,columns=['name','value'])
        elif isinstance(prm, pd.DataFrame):
            _prm = prm.reset_index()
        else:
            _prm = prm.df.reset_index()
        self.df = _prm[['name', 'value']].drop_duplicates(keep='last', inplace=False).set_index('name')\
            .applymap(lambda val : pd.to_numeric(val,errors='ignore'))
        self.filename = None

    def __eq__(self, other):
        """
        Compare two PRM objects for equality.

        Parameters
        ----------
        other : PRM
            The other PRM object to compare with.

        Returns
        -------
        bool
            True if the PRM objects are equal, False otherwise.
        """
        return isinstance(self, PRM) and self.df == other.df

    def __str__(self):
        """
        Return a string representation of the PRM object.

        Returns
        -------
        str
            The string representation of the PRM object.
        """
        return self.to_str()

    def __repr__(self):
        """
        Return a string representation of the PRM object for debugging.

        Returns
        -------
        str
            The string representation of the PRM object. If the PRM object was created from a file, 
            the filename and the number of items in the DataFrame representation of the PRM object 
            are included in the string.
        """
        if self.filename:
            return 'Object %s (%s) %d items\n%r' % (self.__class__.__name__, self.filename, len(self.df), self.df)
        else:
            return 'Object %s %d items\n%r' % (self.__class__.__name__, len(self.df), self.df)

    # use 'g' format for Python and numpy float values
    def set(self, prm=None, gformat=False, **kwargs):
        """
        Set PRM values.

        Parameters
        ----------
        prm : PRM, optional
            The PRM object to set values from. Default is None.
        gformat : bool, optional
            Whether to use 'g' format for float values. Default is False.
        **kwargs
            Additional keyword arguments for setting individual values.

        Returns
        -------
        PRM
            The updated PRM object.
        """
        import numpy as np

        if isinstance(prm, PRM):
            for (key, value) in prm.df.itertuples():
                self.df.loc[key] = value
        elif prm is not None:
            raise Exception('Arguments is not a PRM object')
        for key, value in kwargs.items():
            self.df.loc[key] = float(format(value, 'g')) if gformat and type(value) \
                in [float, np.float16, np.float32, np.float64] else value
        return self

    def to_dataframe(self):
        """
        Convert the PRM object to a DataFrame.

        Returns
        -------
        pd.DataFrame
            The DataFrame representation of the PRM object.
        """
        return self.df

    def to_file(self, prm):
        """
        Save the PRM object to a PRM file.

        Parameters
        ----------
        prm : str
            The filename of the PRM file to save to.

        Returns
        -------
        PRM
            The PRM object.
        """
        self._to_io(prm)
        return self

    #def update(self):
    #    if self.filename is None:
    #        raise Exception('PRM is not created from file, use to_file() method instead')
    #    return self._to_io(self.filename)
    def update(self, name=None, safe=False, debug=False):
        """
        Save PRM file to disk and rename all 3 linked files together: input, LED, SLC if "name" defined.
        If safe=True, save old (small) PRM and LED files and move only (large) SLC file.

        Parameters
        ----------
        name : str, optional
            The new name for the PRM file. Default is None.
        safe : bool, optional
            Whether to use safe mode. Default is False.
        debug : bool, optional
            Whether to enable debug mode. Default is False.

        Returns
        -------
        PRM
            The updated PRM object.
        """
        import shutil
        import os

        if self.filename is None:
            raise Exception('PRM is not created from file, use to_file() method instead')

        if debug:
            print ('Debug mode: only print expected operations but do not perform the actual job')

        # rename linked files
        if name is not None:
            # define current files directory
            dirname0 = os.path.dirname(self.filename)
            # define new files basename
            basename = os.path.splitext(name)[0]
            shortname = os.path.split(basename)[-1]

            # rename PRM file
            if not safe:
                print (f'Remove old PRM file {self.filename} and save new one {name}')
                if not debug:
                    os.remove(self.filename)
            #else:
            #    print (f'Safe mode: remain old PRM file {self.filename} and save new one {name}')
            # will be saved later
            self.filename = name

            input_file0 = os.path.join(dirname0, os.path.split(self.get('input_file'))[-1])
            input_ext = os.path.splitext(input_file0)[1]
            input_file = basename + input_ext
            #print (f'PRM change input_file attribute {input_file0} -> {input_file}')
            self.set(input_file = f'{shortname}{input_ext}')
            if os.path.isfile(input_file0) and not input_file == input_file0:
                if not safe:
                    #print (f'Rename input_file {input_file0} -> {input_file}')
                    if not debug:
                        os.rename(input_file0, input_file)
                else:
                    #print (f'Safe mode: copy input_file {input_file0} -> {input_file}')
                    if not debug:
                        shutil.copy2(input_file0, input_file, follow_symlinks=True)

            SLC_file0 = os.path.join(dirname0, os.path.split(self.get('SLC_file'))[-1])
            SLC_file = basename + '.SLC'
            #print (f'PRM change SLC_file attribute {SLC_file0} -> {SLC_file}')
            self.set(SLC_file = f'{shortname}.SLC')
            if os.path.isfile(SLC_file0) and not SLC_file == SLC_file0:
                #print (f'Rename SLC_file {SLC_file0} -> {SLC_file}')
                if not debug:
                    os.rename(SLC_file0, SLC_file)

            led_file0 = os.path.join(dirname0, os.path.split(self.get('led_file'))[-1])
            led_file = basename + '.LED'
            #print (f'PRM change LED_file attribute {led_file0} -> {led_file}')
            self.set(led_file = f'{shortname}.LED')
            if os.path.isfile(led_file0) and not led_file == led_file0:
                if not safe:
                    #print (f'Rename LED_file {led_file0} -> {led_file}')
                    if not debug:
                        os.rename(led_file0, led_file)
                else:
                    #print (f'Safe mode: copy LED_file {led_file0} -> {led_file}')
                    if not debug:
                        shutil.copy2(led_file0, led_file)

        if debug:
            return self
            #.sel('input_file','SLC_file','led_file')

        return self.to_file(self.filename)

    def to_str(self):
        """
        Convert the PRM object to a string.

        Returns
        -------
        str
            The PRM string.
        """
        return self._to_io()

    def _to_io(self, output=None):
        """
        Convert the PRM object to an IO stream.

        Parameters
        ----------
        output : IO stream, optional
            The IO stream to write the PRM string to. Default is None.

        Returns
        -------
        str
            The PRM string.
        """
        return self.df.reset_index().astype(str).apply(lambda row: (' = ').join(row), axis=1)\
            .to_csv(output, header=None, index=None)

    def sel(self, *args):
        """
        Select specific PRM attributes and create a new PRM object.

        Parameters
        ----------
        *args : str
            The attribute names to select.

        Returns
        -------
        PRM
            The new PRM object with selected attributes.
        """
        return PRM(self.df.loc[[*args]])

    def __add__(self, other):
        """
        Add two PRM objects or a PRM object and a scalar.

        Parameters
        ----------
        other : PRM or scalar
            The PRM object or scalar to add.

        Returns
        -------
        PRM
            The resulting PRM object after addition.
        """
        import pandas as pd
        if isinstance(other, PRM):
            prm = pd.concat([self.df, other.df])
            # drop duplicates
            prm = prm.groupby(prm.index).last()
        else:
            prm = self.df + other
        return PRM(prm)

    def __sub__(self, other):
        """
        Subtract two PRM objects or a PRM object and a scalar.

        Parameters
        ----------
        other : PRM or scalar
            The PRM object or scalar to subtract.

        Returns
        -------
        PRM
            The resulting PRM object after subtraction.
        """
        import pandas as pd
        if isinstance(other, PRM):
            prm = pd.concat([self.df, other.df])
            # drop duplicates
            prm = prm.groupby(prm.index).last()
        else:
            prm = self.df - other
        return PRM(prm)

    def get(self, *args):
        """
        Get the values of specific PRM attributes.

        Parameters
        ----------
        *args : str
            The attribute names to get values for.

        Returns
        -------
        Union[Any, List[Any]]
            The values of the specified attributes. If only one attribute is requested, 
            return its value directly. If multiple attributes are requested, return a list of values.
        """
        out = [self.df.loc[[key]].iloc[0].values[0] for key in args]
        if len(out) == 1:
            return out[0]
        return out

    def shift_atime(self, lines, inplace=False):
        """
        Shift time in azimuth by a number of lines.

        Parameters
        ----------
        lines : float
            The number of lines to shift by.
        inplace : bool, optional
            Whether to modify the PRM object in-place. Default is False.

        Returns
        -------
        PRM
            The shifted PRM object or DataFrame. If 'inplace' is True, returns modified PRM object,
            otherwise, returns a new PRM with shifted times.
        """
        prm = self.sel('clock_start','clock_stop','SC_clock_start','SC_clock_stop') + lines/self.get('PRF')/86400.0
        if inplace:
            return self.set(prm)
        else:
            return prm

    # fitoffset.csh 3 3 freq_xcorr.dat
    # PRM.fitoffset(3, 3, offset_dat)
    # PRM.fitoffset(3, 3, matrix_fromfile='raw/offset.dat')
    @staticmethod
    def fitoffset(rank_rng, rank_azi, matrix=None, matrix_fromfile=None, SNR=20):
        """
        Estimates range and azimuth offsets for InSAR (Interferometric Synthetic Aperture Radar) data.

        Parameters
        ----------
        rank_rng : int
            Number of parameters to fit in the range direction.
        rank_azi : int
            Number of parameters to fit in the azimuth direction.
        matrix : numpy.ndarray, optional
            Array of range and azimuth offset estimates. Default is None.
        matrix_fromfile : str, optional
            Path to a file containing range and azimuth offset estimates. Default is None.
        SNR : int, optional
            Signal-to-noise ratio cutoff. Data points with SNR below this threshold are discarded.
            Default is 20.

        Returns
        -------
        prm : PRM object
            An instance of the PRM class with the calculated parameters.

        Raises
        ------
        Exception
            If both 'matrix' and 'matrix_fromfile' arguments are provided or if neither is provided.
        Exception
            If there are not enough data points to estimate the parameters.

        Usage
        -----
        The function estimates range and azimuth offsets for InSAR data based on the provided input.
        It performs robust fitting to obtain range and azimuth coefficients, calculates scale coefficients,
        and determines the range and azimuth shifts. The resulting parameters are then stored in a PRM object.

        Example
        -------
        fitoffset(3, 3, matrix_fromfile='raw/offset.dat')
        """
        import numpy as np
        import math

        if (matrix is None and matrix_fromfile is None) or (matrix is not None and matrix_fromfile is not None):
            raise Exception('One and only one argument matrix or matrix_fromfile should be defined')
        if matrix_fromfile is not None:
            matrix = np.genfromtxt(matrix_fromfile)

        #  first extract the range and azimuth data
        rng = matrix[np.where(matrix[:,4]>SNR)][:,[0,2,1]]
        azi = matrix[np.where(matrix[:,4]>SNR)][:,[0,2,3]]

        # make sure there are enough points remaining
        if rng.shape[0] < 8:
            raise Exception(f'FAILED - not enough points to estimate parameters, try lower SNR ({rng.shape[0]} < 8)')

        rng_coef = PRM.robust_trend2d(rng, rank_rng)
        azi_coef = PRM.robust_trend2d(azi, rank_azi)

        # print MSE (optional)
        #rng_mse = PRM.robust_trend2d_mse(rng, rng_coef, rank_rng)
        #azi_mse = PRM.robust_trend2d_mse(azi, azi_coef, rank_azi)
        #print ('rng_mse_norm', rng_mse/len(rng), 'azi_mse_norm', azi_mse/len(azi))

        # range and azimuth data ranges
        scale_coef = [np.min(rng[:,0]), np.max(rng[:,0]), np.min(rng[:,1]), np.max(rng[:,1])]

        #print ('rng_coef', rng_coef)
        #print ('azi_coef', azi_coef)

        # now convert to range coefficients
        rshift = rng_coef[0] - rng_coef[1]*(scale_coef[1]+scale_coef[0])/(scale_coef[1]-scale_coef[0]) \
            - rng_coef[2]*(scale_coef[3]+scale_coef[2])/(scale_coef[3]-scale_coef[2])
        # now convert to azimuth coefficients
        ashift = azi_coef[0] - azi_coef[1]*(scale_coef[1]+scale_coef[0])/(scale_coef[1]-scale_coef[0]) \
            - azi_coef[2]*(scale_coef[3]+scale_coef[2])/(scale_coef[3]-scale_coef[2])
        #print ('rshift', rshift, 'ashift', ashift)

        # note: Python x % y expression and nympy results are different to C, use math function
        # use 'g' format for float values as in original GMTSAR codes to easy compare results
        prm = PRM().set(gformat=True,
                        rshift     =int(rshift) if rshift>=0 else int(rshift)-1,
                        sub_int_r  =math.fmod(rshift, 1)  if rshift>=0 else math.fmod(rshift, 1) + 1,
                        stretch_r  =rng_coef[1]*2/(scale_coef[1]-scale_coef[0]),
                        a_stretch_r=rng_coef[2]*2/(scale_coef[3]-scale_coef[2]),
                        ashift     =int(ashift) if ashift>=0 else int(ashift)-1,
                        sub_int_a  =math.fmod(ashift, 1)  if ashift>=0 else math.fmod(ashift, 1) + 1,
                        stretch_a  =azi_coef[1]*2/(scale_coef[1]-scale_coef[0]),
                        a_stretch_a=azi_coef[2]*2/(scale_coef[3]-scale_coef[2]),
                       )

        return prm

    def diff(self, other, gformat=True):
        """
        Compare the PRM object with another PRM object and return the differences.

        Parameters
        ----------
        other : PRM
            The other PRM object to compare with.
        gformat : bool, optional
            Whether to use 'g' format for float values. Default is True.

        Returns
        -------
        pd.DataFrame
            A DataFrame containing the differences between the two PRM objects.
        """
        import pandas as pd
        import numpy as np

        if not isinstance(other, PRM):
            raise Exception('Argument should be PRM class instance')

        df1 = self.df.copy()
        df2 = other.df.copy()

        if gformat:
            fmt = lambda v: format(v, 'g') if type(v) in [float, np.float16, np.float32, np.float64] else v
            df1['value'] = [fmt(value) for value in df1['value']]
            df2['value'] = [fmt(value) for value in df2['value']]

        return pd.concat([df1, df2]).drop_duplicates(keep=False)

    # see about correlation filter
    # https://github.com/gmtsar/gmtsar/issues/86
    def intf(self, other, basedir, topo_ra_fromfile, basename=None, wavelength=200, psize=32, \
            func=None, chunksize=None, debug=False):
        """
        Perform interferometric processing on the input SAR data.

        Parameters
        ----------
        other : PRM
            Another instance of the PRM class representing the second SAR data.
        basedir : str
            Base directory for storing the processed data files.
        topo_ra_fromfile : str
            Path to the topo_ra file used for the calculation.
        basename : str, optional
            Base name for the output files. If not provided, a default name will be generated.
        wavelength : int, optional
            Wavelength of the SAR data in meters. Default is 200 m.
        psize : int, optional
            Werner/Goldstein filter window size in pixels. Default is 32 pixels.
        func : callable, optional
            Custom function to apply on the processed data arrays. Default is None.
        chunksize : int or dict, optional
            Chunk size for dask arrays. Default is None.
        debug : bool, optional
            Enable debug mode. Default is False.

        Returns
        -------
        None

        Notes
        -----
        This method performs interferometric processing on the input SAR data using GMTSAR tools.
        It generates various intermediate and final files, including amplitude and phase data,
        and applies filtering and convolution operations to produce the desired output.
        """
        import os
        import numpy as np
        import xarray as xr
        #from scipy import signal
        import dask_image.ndfilters
        import dask.array

        # constant from GMTSAR code
        thresh = 5.e-21

        if not isinstance(other, PRM):
            raise Exception('Argument "other" should be PRM class instance')

        # define lost class variables due to joblib
        if chunksize is None:
            chunksize = self.chunksize

        # define basename from two PRM names
        if basename is None:
            # S1_20171111_ALL_F3.PRM -> F3
            subswath = os.path.basename(self.filename)[16:18]
            date1    = os.path.basename(self.filename)[3:11]
            date2    = os.path.basename(other.filename)[3:11]
            basename = f'{subswath}_{date1}_{date2}_'
            #print ('basename', basename)

        # make full file name
        fullname = lambda name: os.path.join(basedir, basename + name)
        gmtsar_sharedir = self.gmtsar_sharedir()

        filename_fill_3x3  = os.path.join(gmtsar_sharedir, 'filters', 'fill.3x3')
        filename_gauss5x5  = os.path.join(gmtsar_sharedir, 'filters', 'gauss5x5')
        
        #!conv 1 1 /usr/local/GMTSAR/share/gmtsar/filters/fill.3x3 raw/tmp2.nc raw/corr.nc
        fill_3x3 = np.genfromtxt(filename_fill_3x3, skip_header=1)
        gauss5x5 = np.genfromtxt(filename_gauss5x5, skip_header=1)
        # gauss_dec inconsistent, see https://github.com/gmtsar/gmtsar/issues/706
        gauss_dec, gauss_string = self.make_gaussian_filter(2, 1, wavelength=wavelength)
        #print (gauss_matrix_astext)

        # prepare PRMs for the calculation below
        other.set(self.SAT_baseline(other, tail=9))
        self.set(self.SAT_baseline(self).sel('SC_height','SC_height_start','SC_height_end'))

        # for topo_ra use relative path from PRM files directory
        # use imag.grd=bf for GMT native, C-binary format
        # os.path.join(basedir, f'{subswath}_topo_ra.grd')
        self.phasediff(other, topo_ra_fromfile=topo_ra_fromfile,
                       imag_tofile=fullname('imag.grd=bf'),
                       real_tofile=fullname('real.grd=bf'),
                       debug=debug)

        # making amplitudes
        self.conv(1, 2, filter_file = filename_gauss5x5,
                  output_file=fullname('amp1_tmp.grd=bf'),
                  debug=debug)
        self.conv(1, 2, filter_string=gauss_string,
                  input_file=fullname('amp1_tmp.grd=bf'),
                  output_file=fullname('amp1.grd'),
                  debug=debug)

        other.conv(1, 2, filter_file = filename_gauss5x5,
                   output_file=fullname('amp2_tmp.grd=bf'),
                   debug=debug)
        other.conv(1, 2, filter_string=gauss_string,
                   input_file=fullname('amp2_tmp.grd=bf'),
                   output_file=fullname('amp2.grd'),
                   debug=debug)

        # filtering interferogram
        self.conv(1, 2, filter_file=filename_gauss5x5,
                  input_file=fullname('real.grd=bf'),
                  output_file=fullname('real_tmp.grd=bf'),
                  debug=debug)
        other.conv(1, 2, filter_string=gauss_string,
                   input_file=fullname('real_tmp.grd=bf'),
                   output_file=fullname('realfilt.grd'),
                   debug=debug)
        self.conv(1, 2, filter_file=filename_gauss5x5,
                  input_file=fullname('imag.grd=bf'),
                  output_file=fullname('imag_tmp.grd=bf'),
                  debug=debug)
        other.conv(1, 2, filter_string=gauss_string,
                   input_file=fullname('imag_tmp.grd=bf'),
                   output_file=fullname('imagfilt.grd'),
                   debug=debug)

        # filtering phase
        self.phasefilt(imag_fromfile=fullname('imagfilt.grd'),
                       real_fromfile=fullname('realfilt.grd'),
                       amp1_fromfile=fullname('amp1.grd'),
                       amp2_fromfile=fullname('amp2.grd'),
                       phasefilt_tofile=fullname('phasefilt_phase.grd'),
                       corrfilt_tofile=fullname('phasefilt_corr.grd'),
                       psize=psize,
                       debug=debug)

        # Python post-processing
        # we need to flip vertically results from the command line tools
        realfilt = xr.open_dataarray(fullname('realfilt.grd'), engine=self.engine, chunks=chunksize)
        imagfilt = xr.open_dataarray(fullname('imagfilt.grd'), engine=self.engine, chunks=chunksize)
        amp = np.sqrt(realfilt**2 + imagfilt**2)

        amp1 = xr.open_dataarray(fullname('amp1.grd'), engine=self.engine, chunks=chunksize)
        amp2 = xr.open_dataarray(fullname('amp2.grd'), engine=self.engine, chunks=chunksize)

        # use the same coordinates for all output grids
        # use .values to remove existing attributes from the axes
        # workaround for Google Colab when we cannot save grids with x,y coordinate names
        coords = {'a': amp.y.values, 'r': amp.x.values}

        # making correlation
        tmp = amp1 * amp2
        # fix for "RuntimeWarning: divide by zero encountered in true_divide"
        tmp = xr.where(tmp==0, np.nan, tmp)
        mask = xr.where(tmp >= thresh, 1, np.nan)
        tmp2 = mask * (amp/np.sqrt(tmp))

        #conv = signal.convolve2d(tmp2, fill_3x3/fill_3x3.sum(), mode='same', boundary='symm')
        # use dask rolling window for the same convolution - 1 border pixel is NaN here
        #kernel = xr.DataArray(fill_3x3, dims=['i', 'j'])/fill_3x3.sum()
        #conv = tmp2.rolling(y=3, x=3, center={'y': True, 'x': True}).construct(lat='j', lon='i').dot(kernel)
        # use dask_image package
        kernel = xr.DataArray(fill_3x3, dims=['y', 'x'])/fill_3x3.sum()
        conv = dask_image.ndfilters.convolve(tmp2.data, kernel.data, mode='reflect')
        
        # wrap dask or numpy array to dataarray
        corr_da = xr.DataArray(dask.array.flipud(conv.astype(np.float32)), coords, name='z')
        if func is not None:
            corr_da = func(corr_da)
        if os.path.exists(fullname('corr.grd')):
            os.remove(fullname('corr.grd'))
        corr_da.to_netcdf(fullname('corr.grd'), encoding={'z': self.compression(corr_da.shape, chunksize=chunksize)}, engine=self.engine)

        # make the Werner/Goldstein filtered phase
        phasefilt_phase = xr.open_dataarray(fullname('phasefilt_phase.grd'), engine=self.engine, chunks=chunksize)
        phasefilt_phase_masked = phasefilt_phase * mask
        phasefilt_da = xr.DataArray(dask.array.flipud(phasefilt_phase_masked.astype(np.float32)), coords, name='z')
        if func is not None:
            phasefilt_da = func(phasefilt_da)
        if os.path.exists(fullname('phasefilt.grd')):
            os.remove(fullname('phasefilt.grd'))
        phasefilt_da.to_netcdf(fullname('phasefilt.grd'), encoding={'z': self.compression(phasefilt_da.shape, chunksize=chunksize)}, engine=self.engine)

        # cleanup
        for name in ['amp1_tmp.grd', 'amp2_tmp.grd', 'amp1.grd', 'amp2.grd',
                     'real.grd', 'real_tmp.grd', 'realfilt.grd',
                     'imag.grd', 'imag_tmp.grd', 'imagfilt.grd',
                     'phasefilt_phase.grd', 'phasefilt_corr.grd']:
            filename = fullname(name)
            if not os.path.exists(filename):
                continue
            os.remove(filename)

        return

    # see make_gaussian_filter.c for the original code
    def pixel_size(self):
        """
        Calculate azimuth and range pixel size in meters.

        Returns
        -------
        tuple
            A tuple containing the azimuth and range pixel sizes in meters.

        Notes
        -----
        This method calculates the pixel sizes in the azimuth and range directions based on the provided parameters.
        The azimuth pixel size is determined using the spacecraft velocity, height, and pulse repetition frequency (PRF),
        while the range pixel size is calculated based on the speed of light and the range sampling rate.
        """
        import numpy as np
        from scipy.constants import speed_of_light

        # compute the range and azimuth pixel size
        RE, vel, ht, prf, fs, near_range, num_rng_bins = \
            self.get('earth_radius','SC_vel', 'SC_height', 'PRF', 'rng_samp_rate', 'near_range', 'num_rng_bins')
        #ER, vel, ht, prf, fs, near_range, num_rng_bins
        # real_vel/prf
        azi_px_size = vel / np.sqrt(1 + ht / RE) / prf
        rng_px_size = speed_of_light / fs / 2.0
        # compute the cosine of the looking angle and the surface deviate angle
        a = ht + RE
        far_range = near_range + rng_px_size * num_rng_bins
        rng = (near_range + far_range) / 2.0
        cost = (np.power(a, 2.0) + np.power(rng, 2.0) - np.power(RE, 2.0)) / 2.0 / a / rng
        cosa = (np.power(a, 2.0) + np.power(RE, 2.0) - np.power(rng, 2.0)) / 2.0 / a / RE
        # compute the ground range pixel size
        rng_px_size = rng_px_size / np.sin(np.arccos(cost) + np.arccos(cosa))
        # ground spacing in meters
        return (azi_px_size, rng_px_size)

    # TODO: use PRM parameters to define config parameters
    def snaphu_config(self, defomax=0, **kwargs):
        """
        Generate a configuration file for Snaphu phase unwrapping.

        Parameters
        ----------
        defomax : int, optional
            Maximum number of deformation cycles allowed. Default is 0.
        **kwargs
            Additional configuration parameters in key-value format.

        Returns
        -------
        str
            The generated configuration file as a string.

        Examples
        --------
        Get default SNAPHU config:
        config = sbas.snaphu_config()

        Get custom SNAPHU config with added tiling options:
        config = sbas.snaphu_config(defomax=DEFOMAX, NTILEROW=1, NTILECOL=2, ROWOVRLP=200, COLOVRLP=200)

        Notes
        -----
        This method generates a configuration file for Snaphu, a phase unwrapping software.
        The configuration file includes basic parameters and allows customization by passing additional parameters.

        Custom Parameters
        -----------------
        Additional configuration parameters can be passed as keyword arguments (e.g., `parameter_name=value`).
        Boolean values should be provided as `True` or `False`.
        """
        import os
        # we already use joblib everywhere
        import joblib

        tiledir = os.path.splitext(self.filename)[0]
        n_jobs = joblib.cpu_count()

        conf_basic = f"""
        # basic config
        INFILEFORMAT   FLOAT_DATA
        OUTFILEFORMAT  FLOAT_DATA
        AMPFILEFORMAT  FLOAT_DATA
        CORRFILEFORMAT FLOAT_DATA
        ALTITUDE       693000.0
        EARTHRADIUS    6378000.0
        NEARRANGE      831000
        DR             18.4
        DA             28.2
        RANGERES       28
        AZRES          44
        LAMBDA         0.0554658
        NLOOKSRANGE    1
        NLOOKSAZ       1
        TILEDIR        {tiledir}_snaphu_tiledir
        NPROC          {n_jobs}
        """
        conf_custom = '# custom config\n'
        # defomax can be None
        keyvalues = ([('DEFOMAX_CYCLE', defomax)] if defomax is not None else []) + list(kwargs.items())
        for key, value in keyvalues:
            if isinstance(value, bool):
                value = 'TRUE' if value else 'FALSE'
            conf_custom += f'        {key} {value}\n'
        return conf_basic + conf_custom

