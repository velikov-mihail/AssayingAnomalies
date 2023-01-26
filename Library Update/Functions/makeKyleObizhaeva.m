function vov = makeKyleObizhaeva()
% PURPOSE: This functions creates the VoV Effective Spread (!!!) measure 
% from Kyle and Obizhaeva (ECTA, 2016) following the implementation of 
% Fong, Holden, and Tobek (WP, 2018). Also used as one of the four 
% low-freqency effective spread measures in Chen and Velikov (JFQA, 2022)
%------------------------------------------------------------------------------------------
% USAGE:   
% vov = makeKyleObizhaeva()              
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - N/A
%------------------------------------------------------------------------------------------
% Output:
%        -vov - a matrix with the effective spread estimates 
%------------------------------------------------------------------------------------------
% Examples:
%
% vov = makeKyleObizhaeva()              
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
%  2. Fong, K., C. Holden, and O. Tobek, 2018, Are volatility over volume
%  liquidity proxies useful for global or US research, Working paper.
%  3. Kyle, A. and A. Obizhaeva, 2016, Market microstructure invariance:
%  Empirical hypotheses, Econometrica, 84 (4): 1345-1404
%  4. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('Now working on Kyle and Obizhaeva''s (2016) volume-over-volatility effective spread construction. Run started at %s.\n', char(datetime('now')));

% Load the necessary variables
load dvol
load dret
load ddates
load dates
load ret
load dprc

% Store the constants
a = 8.0;
b = 2/3;
c = 1/3;

% Get dollar volume
dvol = dvol .* abs(dprc);

% Pull the inflation series from FRED
% Initialize the cpi vector
cpi = nan(size(dates));

% Get the end date
finalYear = num2str(floor(dates(end)/100));
endDate = [finalYear, '-12-31'];

% Pull the CPIAUCNS series from FRED
fredStruct = getFredData('CPIAUCNS', [], endDate, 'lin', 'm', 'eop');

% Convert the FRED dates to datetime
fredDates = datetime(fredStruct.Data(:,1), 'ConvertFrom', 'datenum');
fredDates = 100*year(fredDates) + ...
                month(fredDates);

% Assign the cpi data to the veector
[~, indDates, indFred] = intersect(dates, fredDates, 'legacy');
cpi(indDates) = fredStruct.Data(indFred,2);

% Use FHT's (2018) normalization 
cpi = cpi/cpi(dates==200001); 

% Initalize the VoV matrix & store number of months
vov = nan(size(ret));
nMonths = length(dates);


for i = 1:nMonths
    % Find all days in the currenty month
    monthInd = find(floor(ddates/100) == dates(i));
    % Find all eligible stocks (based on FHT's filters
    stocksInd = find( sum(dvol(monthInd,:) > 0,  1) >= 5 &  ...
                  sum(abs(dret(monthInd,:)) > 0, 1) >= 11);

    % Calculate the VoV 
    retStd = std(dret(monthInd, stocksInd), 0, 1, 'omitnan');
    volMean = mean(dvol(monthInd,stocksInd),1,'omitnan') / cpi(i);
    num = a * (retStd .^ b);    
    den = (volMean) .^ c;
    vov(i, stocksInd) = (num)./(den);
end

