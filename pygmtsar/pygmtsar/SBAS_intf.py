# ----------------------------------------------------------------------------
# PyGMTSAR
# 
# This file is part of the PyGMTSAR project: https://github.com/mobigroup/gmtsar
# 
# Copyright (c) 2021, Alexey Pechnikov
# 
# Licensed under the BSD 3-Clause License (see LICENSE for details)
# ----------------------------------------------------------------------------
from .SBAS_topo_ra import SBAS_topo_ra

class SBAS_intf(SBAS_topo_ra):

    def intf(self, subswath, pair, **kwargs):
        """
        Generate an interferogram for a given pair of dates representing synthetic aperture radar (SAR) images.

        Parameters:
        ----------
        subswath : int
            The subswath number to use.

        pair : tuple
            A tuple of strings representing the dates for the pair of images in the form 'YYYYMMDD'.

        kwargs : dict, optional
            Additional keyword arguments for the PRM.intf() method. This can be used to customize the interferogram generation process.

        Raises:
        ------
        OSError
            If the required input files or directories cannot be accessed.

        Notes:
        ------
        This method generates an interferogram by first creating PRM objects for the reference (ref) and repeat (rep) images. It then calls the intf() method of the PRM object for the reference image, passing the PRM object for the repeat image and any additional keyword arguments. The output is an interferogram stored as a grid file.
        """
        import os

        # extract dates from pair
        date1, date2 = pair

        prm_ref = self.PRM(subswath, date1)
        prm_rep = self.PRM(subswath, date2)

        topo_ra_file = os.path.join(self.basedir, f'F{subswath}_topo_ra.grd')
        #print ('SBAS intf kwargs', kwargs)
        prm_ref.intf(prm_rep,
                     basedir=self.basedir,
                     topo_ra_fromfile = topo_ra_file,
                     **kwargs)

    def intf_parallel(self, pairs, n_jobs=-1, **kwargs):
        """
        Build interferograms for all the subswaths in parallel.

        Parameters
        ----------
        pairs : list
            List of date pairs (baseline pairs).
        n_jobs : int, optional
            Number of parallel processing jobs. n_jobs=-1 means all the processor cores used.
        wavelength : float, optional
            Filtering wavelength in meters.
        psize : int, optional
            Patch size for modified Goldstein adaptive filter (power of two).
        func : function, optional
            Post-processing function usually used for decimation.

        Returns
        -------
        None

        Examples
        --------
        For default 60m DEM resolution and other default parameters use command below:
        pairs = [sbas.to_dataframe().index.unique()]
        decimator = lambda dataarray: dataarray.coarsen({'y': 4, 'x': 4}, boundary='trim').mean()
        sbas.intf_parallel(pairs, func=decimator)
        """
        import pandas as pd
        import numpy as np
        from tqdm.auto import tqdm
        import joblib
        import os

        # convert pairs (list, array, dataframe) to 2D numpy array
        pairs = self.pairs(pairs)[['ref', 'rep']].astype(str).values

        subswaths = self.get_subswaths()

        # for now (Python 3.10.10 on MacOS) joblib loads the code from disk instead of copying it
        kwargs['chunksize'] = self.chunksize
        
        # this way does not work properly for long interferogram series on MacOS
        # see https://github.com/mobigroup/gmtsar/commit/3eea6a52ddc608639e5e06306bce2f973a184fd6
        #with self.tqdm_joblib(tqdm(desc='Interferograms', total=len(pairs)*len(subswaths))) as progress_bar:
        #    joblib.Parallel(n_jobs=n_jobs)(joblib.delayed(self.intf)(subswath, pair, **kwargs) \
        #        for subswath in subswaths for pair in pairs)

        # workaround: start a set of jobs together but not more than available cpu cores at once
        from joblib.externals import loky
        if n_jobs == -1:
            n_jobs = joblib.cpu_count()
        # create list of arrays [subswath, date1, date2] where all the items are strings
        subpairs = [[subswath, pair[0], pair[1]] for subswath in subswaths for pair in pairs]
        n_chunks = int(np.ceil(len(subpairs)/n_jobs))
        chunks = np.array_split(subpairs, n_chunks)
        #print ('n_jobs', n_jobs, 'n_chunks', n_chunks, 'chunks', [len(chunk) for chunk in chunks])
        with tqdm(desc='Interferograms', total=len(subpairs)) as pbar:
            for chunk in chunks:
                loky.get_reusable_executor(kill_workers=True).shutdown(wait=True)
                with joblib.parallel_backend('loky', n_jobs=n_jobs):
                    # convert string subswath to integer value
                    joblib.Parallel()(joblib.delayed(self.intf)(int(subswath), [date1, date2], **kwargs) \
                        for (subswath,date1,date2) in chunk)
                    pbar.update(len(chunk))
