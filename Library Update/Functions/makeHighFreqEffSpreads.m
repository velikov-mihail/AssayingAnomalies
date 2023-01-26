function hf_spreads = makeHighFreqEffSpreads(fileName)
% PURPOSE: This function creates the high-frequency effective
% spread estimate as used in Chen and Velikov (JFQA, 2022)
%------------------------------------------------------------------------------------------
% USAGE:   
% hf_spreads = makeHighFreqEffSpreads(fileName)              
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -fileName - path to file with high-frequency effective spread estimates
%------------------------------------------------------------------------------------------
% Output:
%        -chl - a matrix with the effective spread estimates 
%------------------------------------------------------------------------------------------
% Examples:
%
% hf_spreads = makeHighFreqEffSpreads(fileName)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Chen, A. and M. Velikov, 2022, Zeroing in on the expected return on 
%  anomalies, Journal of Financial and Quantitative Analysis, Forthcoming.
%  2. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.


% Timekeeping
fprintf('Starting TAQ+ISSM construction at %s.\n', char(datetime('now')));

% Read in the stored estimates
opts = detectImportOptions(fileName);
data = readtable(fileName,opts);

% Clean them up
data = data(:,{'permno','yearm','espread_pct_mean','espread_pct_month_end','espread_n'});
data.Properties.VariableNames = {'permno','date','ave','monthend','n'};

% Load the variables we need to match 
load permno
load dates
load ret

% Initialize the high-frequency spreads structure
hf_spreads = struct;
hf_spreads.ave      = nan(size(ret));
hf_spreads.n        = nan(size(ret));
hf_spreads.monthend = nan(size(ret));

% Store the numbre of observations
nObs = height(data);

for i=1:nObs  
    % Find the corresponding month and permno
    r = find(dates  == data.date(i));
    c = find(permno == data.permno(i));
    if ~isempty(r+c)
        % Store the variables in the structure
        hf_spreads.ave(r,c)      = data.ave(i)/100;
        hf_spreads.n(r,c)        = data.n(i);
        hf_spreads.monthend(r,c) = data.monthend(i);
    end
end

