function downloadChenZimmermanFiles(signalFileID, docFileID)
% PURPOSE: This function runs a univariate sort and calculates portfolio
% average returns and estimates alphas and loadings on a factor model
%------------------------------------------------------------------------------------------
% USAGE:   
% downloadChenZimmermanFiles(signalFileID, docFileID)                                         
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -signalFileID - Google drive id of their
%                        signed_predictors_dl_wide.zip file, which contains
%                        the signals data
%        -docFileID - Google drive id of their
%                        SignalDocumentation.xlsx file, which contains
%                        the documentation information for the signals
%------------------------------------------------------------------------------------------
% Output:
%------------------------------------------------------------------------------------------
% Examples:
%
% downloadChenZimmermanFiles(signalFileID, docFileID)                                     
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by getChenZimmermanAnomalies()
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.


% Find the directory for this function
functionPath = mfilename('fullpath');
dirSepIndex = strfind(functionPath, 'Functions');                                  

filePath = regexprep([functionPath(1:dirSepIndex-1),'Data\Anomalies\'], '\', '/');

% Get the anomaly signal data first    
fileName = 'signed_predictors_dl_wide.zip';
getGoogleDriveData(fileName, signalFileID, filePath);

if strcmp(docFileID, '18DvZPscKsD0_ZeeUMjyXhF1qn0emDVaj')
    fileName = 'SignalDocumentation.xlsx';
elseif strcmp(docFileID, '1PDFl3pKwbY8DH5S9PWH_Op16HPo2wZL1')
    fileName = 'SignalDoc.csv';
end

getGoogleDriveData(fileName, docFileID, filePath);
