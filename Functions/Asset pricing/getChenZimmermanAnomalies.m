function [anoms, labels, anomaly_summary] = getChenZimmermanAnomalies()
% PURPOSE: This function (downloads and) loads the anomaly signals from the
% Chen and Zimmerman (2022) open-source asset pricing library
%------------------------------------------------------------------------------------------
% USAGE:   
% [anoms, labels, anomaly_summary] = getChenZimmermanAnomalies()     
% The function checks whether one of the following two pairs of files from
% the Chen and Zimmerman (2022) open-source asset pricing library were 
% downloaded: 
% 
% April 2021 release:
% https://drive.google.com/file/d/1-1RUq2wUADu_ncvQJCYY3wxDhqhHxBow/view
% https://docs.google.com/spreadsheets/d/18DvZPscKsD0_ZeeUMjyXhF1qn0emDVaj/edit#gid=70837236
%
% March 2022 release:
% https://drive.google.com/file/d/1OK1bYpaq8xUSLElgJiVDdqizP5YJOzHa/view?usp=sharing
% https://drive.google.com/file/d/1PDFl3pKwbY8DH5S9PWH_Op16HPo2wZL1/view?usp=sharing
% If not it download the March 2022 release programatically, although the 
% file ID's are hard coded, so they need to be updated manually every year. 
%------------------------------------------------------------------------------------------
% Required Inputs:
%------------------------------------------------------------------------------------------
% Output:
%        - anoms - a 3-d numeric array corresponding to (nMonths x nStocks x nAnoms)
%        - labels - a vector of Acronyms for each anomaly
%        - anomaly_summary - a table with documentation for anomalies (publication dates, 
%                           sample periods, etc.)
%------------------------------------------------------------------------------------------
% Examples:
%
% [anoms, labels, anomaly_summary] = getChenZimmermanAnomalies();                                     
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses getAnomalySignals(), getGoogleDriveData()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Chen, A. and T. Zimmermann, 2022, Open source cross-sectional asset
%  pricing, Critical Finance Review, 27 (2), 207-264
%  2. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.



% Check if the two files were downloaded
if  ~exist('signed_predictors_dl_wide.csv', 'file') || ...
   (~exist('SignalDocumentation.xlsx', 'file') && ~exist('SignalDoc.csv', 'file'))
    
%     % These are the file IDs from the April, 2021 release. 
%     signalFileID = '1-1RUq2wUADu_ncvQJCYY3wxDhqhHxBow';
%     docFileID = '18DvZPscKsD0_ZeeUMjyXhF1qn0emDVaj';
     
    % These are the file IDs from the March, 2022 release. 
    signalFileID = '1OK1bYpaq8xUSLElgJiVDdqizP5YJOzHa';
    docFileID = '1PDFl3pKwbY8DH5S9PWH_Op16HPo2wZL1';
    
    downloadChenZimmermanFiles(signalFileID, docFileID)
    
    % Make sure we downloaded them
    if  ~exist('signed_predictors_dl_wide.csv', 'file') && ...
   (~exist('SignalDocumentation.xlsx', 'file') || ~exist('SignalDoc.csv', 'file'))
        error('\nChen-Zimmerman files not on path. Please, check their file ID numbers and/or download files from https://www.openassetpricing.com/.\n\n');
    end
end

% Read in the anomaly signals. This requires over ~70GB of RAM if your data goes back to 1925
[anoms, labels] = getAnomalySignals('signed_predictors_dl_wide.csv', 'permno', 'yyyymm');
fprintf('Done getting signals at at %s.\n',char(datetime('now')));


% WRDS doesn't let CZ share these three anomalies, so we need to add them
nAnoms = size(anoms, 3);
load prc
load ret
load me
anoms(:, : ,nAnoms+1) = -abs(prc);
anoms(:, : ,nAnoms+2) = -ret;
anoms(:, : ,nAnoms+3) = -me;
labels(nAnoms+1) = {'Price'};
labels(nAnoms+2) = {'STreversal'};
labels(nAnoms+3) = {'Size'};

if exist('SignalDocumentation.xlsx','file')
    % Read in the anomaly documentation "BasicInfo" sheet
    opts = detectImportOptions('SignalDocumentation.xlsx','Sheet','BasicInfo');
    data = readtable('SignalDocumentation.xlsx',opts);
    
    % Store it in a table called anomaly_summary
    anomaly_summary = data(ismember(data.Cat_Signal,{'Predictor'}),:);
    
    % Read in the "AddInfo" sheet
    opts = detectImportOptions('SignalDocumentation.xlsx','Sheet','AddInfo');
    data = readtable('SignalDocumentation.xlsx',opts);
    
    % Add data on weighting, portfolios, etc. to the anomaly_summary table
    opts.VariableTypes(strcmp(opts.VariableNames,'LSQuantile')) = {'double'};
    data = data(ismember(data.Cat_SignalFormula,{'Predictor'}),:);
    colList = {'Acronym','StockWeight','LSQuantile','PortfolioPeriod','StartMonth','Filter','QuantileFilter'};
    data = data(:,colList);
    anomaly_summary = outerjoin(anomaly_summary, data, 'MergeKeys', 1, ...
                                                       'Type', 'Left');
    anomaly_summary.LSQuantile = str2double(anomaly_summary.LSQuantile);
else
    % Read the summary spreadsheet
    opts = detectImportOptions('SignalDoc.csv');    
    anomaly_summary = readtable('SignalDoc.csv', opts);
    
    % Drop the non-predictors
    indToDrop = ~strcmp(anomaly_summary.Cat_Signal, 'Predictor');
    anomaly_summary(indToDrop, :) = [];    
end

% Sort them to be in the same order
[labels, I] = sort(labels);
anoms = anoms(:, :, I);

[~, I] = sort(anomaly_summary.Acronym);
anomaly_summary = anomaly_summary(I, :);

