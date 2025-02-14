# ----------------------------------------------------------------------------
# PyGMTSAR
# 
# This file is part of the PyGMTSAR project: https://github.com/mobigroup/gmtsar
# 
# Copyright (c) 2022, Alexey Pechnikov
# 
# Licensed under the BSD 3-Clause License (see LICENSE for details)
# ----------------------------------------------------------------------------
from .SBAS_unwrap_snaphu import SBAS_unwrap_snaphu

class SBAS_unwrap(SBAS_unwrap_snaphu):

    def unwrap_parallel(self, pairs=None, mask=None, chunksize=None, n_jobs=-1, **kwargs):
        """
        Unwraps phase using SNAPHU in parallel for multiple interferogram pairs.

        This function unwraps the phase of multiple interferograms using the Statistical-cost, Network-flow Algorithm
        for Phase Unwrapping (SNAPHU) with user-defined parameters. The unwrapped phase is saved as grid files
        in the working directory. This function is designed to process multiple interferograms in parallel, 
        leveraging the available computational resources.

        Parameters
        ----------
        pairs : list, tuple, array or pandas.DataFrame, optional
            A list or array of pairs of reference and repeat dates, or a DataFrame with 'ref' and 'rep' columns.

        mask : str or xarray.DataArray, optional
            A user-defined mask for radar coordinates, default is None.

        n_jobs : int, optional
            The number of jobs to run in parallel. -1 means using all available processors, default is -1.

        **kwargs : dict
            Additional keyword arguments to be passed to the unwrap function.

        Returns
        -------
        None
            This function saves the unwrapped phase to disk as grid files and does not return any values.

        Examples
        --------
        Simplest unwrapping:
        sbas.unwrap_parallel(pairs)

        Filter low-coherence areas with common correlation threshold 0.75:
        sbas.unwrap_parallel(pairs, threshold=0.075)

        Unwrap with coherence threshold 0.075 and fill NODATA gaps:
        interpolator = lambda corr, unwrap: sbas.nearest_grid(unwrap).where(corr>=0)
        sbas.unwrap_parallel(pairs, threshold=0.075, func=interpolator)

        Unwrap with coherence threshold 0.075 and apply land mask:
        cleaner = lambda corr, unwrap: xr.where(corr>=0.075, unwrap, np.nan)
        sbas.unwrap_parallel(pairs, threshold=0.075, mask=landmask_ra, func=cleaner)

        Unwrap with coherence threshold 0.075 and use SNAPHU tiling for faster processing and smaller RAM usage:
        cleaner = lambda corr, unwrap: xr.where(corr>=0.075, unwrap, np.nan)
        conf = sbas.PRM().snaphu_config(NTILEROW=1, NTILECOL=2, ROWOVRLP=200, COLOVRLP=200)
        sbas.unwrap_parallel(pairs, n_jobs=1, threshold=0.075, func=cleaner, conf=conf)

        Notes
        -----
        This function unwraps phase using SNAPHU in parallel for multiple interferogram pairs.
        The unwrapped phase is saved as grid files in the working directory.
        Additional keyword arguments can be passed to customize the unwrapping process.
        """
        import xarray as xr
        import pandas as pd
        from tqdm.auto import tqdm
        import joblib
        import os

        # for now (Python 3.10.10 on MacOS) joblib loads the code from disk instead of copying it
        kwargs['chunksize'] = chunksize

        def unwrap_tiledir(pair, **kwargs):
            # define unique tiledir name for parallel processing
            if 'conf' in kwargs:
                dirpath = self.get_filenames(None, [pair], 'snaphu_tiledir')[0][:-4]
                kwargs['conf'] += f'    TILEDIR {dirpath}'
            return self.unwrap(pair, **kwargs)

        # convert pairs (list, array, dataframe) to 2D numpy array
        pairs = self.pairs(pairs)[['ref', 'rep']].astype(str).values
        
        # materialize lazy mask
        if mask is not None and isinstance(mask, xr.DataArray):
            mask_filename = self.get_filenames(None, None, 'unwrapmask')
            if os.path.exists(mask_filename):
                os.remove(mask_filename)
            # workaround to save NetCDF file correct
            mask.rename('mask').rename({'y':'a','x':'r'}).\
                to_netcdf(mask_filename, encoding={'mask': self.compression(mask.shape, chunksize=chunksize)}, engine=self.engine)
            kwargs['mask'] = 'unwrapmask'

        # save results to NetCDF files
        kwargs['interactive'] = False

        with self.tqdm_joblib(tqdm(desc='Unwrapping', total=len(pairs))) as progress_bar:
            joblib.Parallel(n_jobs=n_jobs)(joblib.delayed(unwrap_tiledir)(pair, **kwargs) for pair in pairs)

    def get_unwrapmask(self, geocode=False):
        """
        Retrieves the unwrapping mask created during the unwrap_parallel function execution.

        This function returns the unwrapping mask that was created during the unwrap_parallel() function call.
        The mask can be returned in either radar or geocoded coordinates.

        Parameters
        ----------
        geocode : bool, optional
            If True, the unwrapping mask will be converted to geocoded coordinates, default is False.

        Returns
        -------
        unwrapmask : xarray.DataArray
            The unwrapping mask as an xarray.DataArray object in either radar or geocoded coordinates.

        Raises
        ------
        Exception
            If the unwrapping mask does not exist, an exception will be raised, suggesting the user call
            the unwrap_parallel() function with the mask first.

        """
        import xarray as xr
        import numpy as np
        import os

        unwrapmask_filename = self.get_filenames(None, None, 'unwrapmask')
        if not os.path.exists(unwrapmask_filename):
            raise Exception('Unwrapping mask does not exist, call unwrap_parallel() function with the mask first')
        # this function renames coordinates
        unwrapmask = self.open_grids(None, 'unwrapmask')
        if geocode:
            # datatypes convertion required
            return self.intf_ra2ll(unwrapmask.astype(np.int8)).astype(bool)
        return unwrapmask
