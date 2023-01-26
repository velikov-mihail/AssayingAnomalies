function gibbs = makeGibbs(fileName)
% PURPOSE: This function creates the Hasbrouck (JF, 2009) effective spread
% estimate as used in Novy-Marx and Velikov (RFS, 2016) and Chen and
% Velikov (JFQA, 2022)
%------------------------------------------------------------------------------------------
% USAGE:   
% gibbs = makeGibbs(fileName)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -fileName - path to file with Hasbrouck effective spread estimates
%------------------------------------------------------------------------------------------
% Output:
%        -gibbs - a matrix with the effective spread estimates 
%------------------------------------------------------------------------------------------
% Examples:
%
% gibbs = makeGibbs(fileName)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Hasbrouck, J., 2009, Trading costs and returns for U.S. equities:
%  Estimating effective costs from daily data, Journal of Finance, 64 (3):
%  1445-1477
%  2. Chen, A. and M. Velikov, 2022, Zeroing in on the expected return on 
%  anomalies, Journal of Financial and Quantitative Analysis, Forthcoming.
%  3. Novy-Marx, R. and M. Velikov, 2016, A taxonomy of anomalies and their
%  costs of trading, Review of Financial Studies, 29 (1): 104-147
%  4. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('Now working on Hasbrouck''s (2009) Gibbs construction. Run started at %s.\n', char(datetime('now')));

% Read in the stored estimates
opts = detectImportOptions(fileName);
data = readtable(fileName,opts);

% Clean them up
data = data(:,{'permno','year','c'});
data(isnan(data.c), :) = [];

% In some years there is more than one estimate, so we'll average them
data=varfun(@nanmean, data, 'GroupingVariables', {'permno','year'});

% Clean it up again
data.GroupCount=[];
data.Properties.VariableNames{'nanmean_c'}='c';

% Load the CRSP link table
load crsp_link

% Create an year variable
crsp_link.year = floor(crsp_link.dates/100);

% Merge
mergedData = outerjoin(crsp_link, data, 'Type', 'Left', 'MergeKeys', 1);

% Clean up the year variable and unstack
mergedData.year=[];
gibbs = unstack(mergedData, 'c', 'dates');
gibbs = table2array(gibbs(:,2:end))';

% Multiply by 2 to be consistent with the other spread measures. We'll divide by two later.
gibbs = 2*gibbs; 

