function setAssayPath(fileName)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It is an auxiliary function that sets the path when executing
% the test_signal.m script
%------------------------------------------------------------------------------------------
% USAGE:   
% setAssayPath(fileName)              % Creates a log file in the main directory                                 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.COMPUSTATVariablesFileName - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% setAssayPath(fileName)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       None
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Index of directory separators
dirSepIndex = strfind(fileName, filesep);                                  

% Path to the package
fullPath    = fileName(1:dirSepIndex(end));                                

% Add the relevant folders (with subfolders) to the path
restoredefaultpath;
addpath(fullPath)
addpath(genpath([fullPath, 'Data']))
addpath(genpath([fullPath, 'Functions']))
cd(fullPath)

% Check if Scratch\Cookbook exists, make it if not
if ~exist([fullPath, 'Scratch'], 'dir')
  mkdir([fullPath,'Scratch']);
  addpath([fullPath, 'Scratch']);
else 
  addpath([fullPath, 'Scratch']);
end

% Check if Scratch\Assay exists, make it if not
if ~exist([fullPath, 'Scratch', filesep, 'Assay'], 'dir')
  mkdir([fullPath, 'Scratch', filesep, 'Assay']);
  addpath([fullPath, 'Scratch', filesep, 'Assay']);
else 
  addpath([fullPath, 'Scratch', filesep, 'Assay']);
end