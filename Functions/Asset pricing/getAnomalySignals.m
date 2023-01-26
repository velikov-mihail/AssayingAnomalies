function [anoms, labels] = getAnomalySignals(fileName,permnoColumn,datesColumn,varargin)
% PURPOSE: Creates a three-dimensional numerical array with anomaly signals
% from a .csv file that contains signal data in (permno x month x var(s)) format
%------------------------------------------------------------------------------------------
% USAGE: 
%       [anoms, labels] = getAnomalySignals(fileName, permnoColumn, datesColumn);                   
%       [anoms, labels] = getAnomalySignals(fileName, permnoColumn, datesColumn, Name, Value);      
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -fileName - name of file that contains anomaly signal data at in (permno x month x var(s)) format
%       -permnoColumn - a scalar or character array indicating the column with permnos
%       -datesColumn - a scalar or character array indicating the column with dates
% Optional Name-Value Pair Arguments:
%       -anomalyNames - an optional argument indicating anomaly columns to use. Could be:
%               * numerical array (e.g. 5; [5 8]; [6:10])
%               * character array (e.g., 'value')
%               * cell array (e.g., {'size','value'})
%       -datesFromat - an optional character array indicating format of dates vector
%------------------------------------------------------------------------------------------
% Output:
%       -anoms -a three-dimensional numerical array with anomaly signals (nmonths x nstocks x nanoms)
%       -labels -a cell array with anomaly names (1 x nanoms)
%------------------------------------------------------------------------------------------
% Examples: 
%       fileName = 'novyMarxVelikovAnomalies.csv';
%       [anoms, labels] = getAnomalySignals(fileName, 'permno', 'dates');     downloads all 23 anomalies from Novy-Marx and Velikov (RFS, 2013)
%       [anoms, labels] = getAnomalySignals(fileName, 1, 2);              	  you can use numbers instead of column headers       
%       [anoms, labels] = getAnomalySignals(fileName, 'permno', 'dates',...
%                                            'anomalyNames',{'size', 'value'});    downloads size and value only
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Parse the inputs
p = inputParser;
p.KeepUnmatched = true;
validChar = @(x) ischar(x);
validNumChar = @(x) isnumeric(x) || ischar(x);
validNumCharCell = @(x) isnumeric(x) || ischar(x) || iscell(x);
addRequired(p, 'fileName', validChar);
addRequired(p, 'permnoColumn', validNumChar);
addRequired(p, 'datesColumn', validNumChar);
addParameter(p, 'anomalyNames', '', validNumCharCell);
addParameter(p, 'datesFormat', 'yyyymm', validChar);
parse(p, fileName, permnoColumn, datesColumn, varargin{:});


% Check if the file exists
[~, urlStatus] = urlread(fileName);
if ~exist(fileName, 'file') && ~urlStatus
    error('Wrong file name.');
end

% Read in the import options for the file
opts = detectImportOptions(fileName);

% Check if valid permno column when it's a character array
validPermnoColumn = (ischar(permnoColumn) && sum(ismember(opts.VariableNames,permnoColumn))==1) ||  ... % if user entered name of column
                    (isnumeric(permnoColumn) && permnoColumn<length(opts.VariableNames));
if ~validPermnoColumn
    error('Wrong permno column.');
end

% Check if valid dates column when it's a character array
validDatesColumn = (ischar(datesColumn) && sum(ismember(opts.VariableNames,datesColumn))==1) ||  ... % if user entered name of column
                    (isnumeric(datesColumn) && datesColumn<length(opts.VariableNames));
if ~validDatesColumn
    error('Wrong dates column.');
end

% Check if permno is a column number
if isnumeric(permnoColumn)
    permnoColumn = char(opts.VariableNames(permnoColumn));
end 

% Check if dates is a column number
if isnumeric(datesColumn)
    datesColumn = char(opts.VariableNames(datesColumn));
end

% Store the permnos and dates in a cell array.
permnoDatesCell = [cellstr(permnoColumn) cellstr(datesColumn)];

% Check if user entered specific anomalies
if ~strcmp(p.Results.anomalyNames,'')    
    % Check if entry was valid
    validAnomColumn = (ischar(p.Results.anomalyNames) && sum(ismember(opts.VariableNames, p.Results.anomalyNames))==1) ||  ...                              % if user entered name of single column
                      (iscell(p.Results.anomalyNames) && sum(ismember(opts.VariableNames, p.Results.anomalyNames))==length(p.Results.anomalyNames)) ||  ... % if user entered name of multiple columns
                      (isnumeric(p.Results.anomalyNames) && max(p.Results.anomalyNames) < length(opts.VariableNames));                                      % if user entered column number(s)
    if ~validAnomColumn
        error('Wrong anomaly header names.');
    end
    
    % Figure out the labels of the anomaly signals
    if isnumeric(p.Results.anomalyNames)        
        labels = opts.VariableNames(p.Results.anomalyNames);
    elseif ischar(p.Results.anomalyNames)
        labels = cellstr(anomColumn);
    else
        if size(p.Results.anomalyNames, 1) > size(p.Results.anomalyNames, 2)
            labels = p.Results.anomalyNames';
        else
            labels = p.Results.anomalyNames;
        end
    end
       
else    
    % Assume all other columns are anomalies
    labels = opts.VariableNames(~ismember(opts.VariableNames,permnoDatesCell)); 
end

% Select the columns to import
opts.SelectedVariableNames = [permnoDatesCell labels];
opts.VariableTypes = repmat({'double'}, 1, length(opts.VariableTypes));

% Import the data 
if ~strcmp(p.Results.datesFormat,'yyyymm') 
    % This allows for user-defined dates format
    opts.VariableTypes(find(strcmp(opts.VariableNames, datesColumn))) = {'char'};
    data = readtable(fileName, opts);
    data.(datesColumn) = datetime(data.(datesColumn), 'InputFormat', p.Results.datesFormat);
    data.(datesColumn) = 100*year(data.(datesColumn)) + month(data.(datesColumn));
else
    data = readtable(fileName,opts);
end

% Load permno and dates vectors
load permno
load dates

% Store a few constants
nStocks = length(permno);
nMonths  = length(dates);
nAnoms  = length(labels);
nObs = nStocks*nMonths;

% Initialize the anoms 3-d array
anoms = nan(nMonths, nStocks, nAnoms);

% Create nMonths x nStocks matrics
rptdPermno = repmat(permno', nMonths, 1);
rptdDates  = repmat(dates, 1, nStocks);

% Reshape them
rshpdPermno = reshape(rptdPermno, nObs, 1);
rshpdDates  = reshape(rptdDates, nObs, 1);

% Make a table we'll use to merge the anomalies
leftMergeTable = array2table([rshpdPermno rshpdDates]);
leftMergeTable.Properties.VariableNames = permnoDatesCell;                  

% Merge the data
mergedTable = outerjoin(leftMergeTable, data, 'Type', 'Left', ...
                                              'MergeKeys', 1);
clear data leftMergeTable

% Unstack each anomaly
for i=1:nAnoms
    thisTable = mergedTable(:, [permnoDatesCell labels(i)]);
    thisSignal = unstack(thisTable, labels(i), datesColumn, 'VariableNamingRule', 'modify');
    thisSignal.(permnoColumn) = [];
    anoms(:, :, i) = table2array(thisSignal)';    
end
