function makeCRSPMonthlyData(Params)
% PURPOSE: This function uses the stored required tables from the CRSP
% monthly file to create matrices of dimensions number of months by number
% of stocks for all variables downloaded from the monthly CRSP file
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCRSPMonthlyData(Params)              % Turns the CRSP monthly file into matrices
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
% makeCRSPMonthlyData(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on making variables from CRSP. Run started at %s.\n', char(datetime('now')));

% Store the CRSP directory path
crspDirPath = [Params.directory, 'Data/CRSP/'];

% Read the CRSP monthly stock file
crspMSFPath = [crspDirPath, 'crsp_msf.csv'];
opts        = detectImportOptions(crspMSFPath);
crsp_msf    = readtable(crspMSFPath, opts);
fprintf('CRSP_MSF file loaded. It contains %d rows and %d columns.\n',height(crsp_msf),width(crsp_msf));

% Convert dates to YYYYMM format
crsp_msf.dates = 100*year(crsp_msf.date) + month(crsp_msf.date);

% Read the CRSP monthly stock file with share code information
crspMSEExchPath   = [crspDirPath, 'crsp_mseexchdates.csv'];
opts              = detectImportOptions(crspMSEExchPath);
crsp_mseexchdates = readtable(crspMSEExchPath, opts);
crsp_mseexchdates = crsp_mseexchdates(:,{'permno','namedt','nameendt', ...
                                         'shrcd','exchcd','siccd'});

% Merge the share code from the header file to CRSP_MSF
crsp_msf = outerjoin(crsp_msf, crsp_mseexchdates, 'Type', 'Left', ...
                                                  'Keys', 'permno', ...
                                                  'RightVariables', {'namedt','nameendt','shrcd','exchcd','siccd'});
idxToDrop = crsp_msf.date < crsp_msf.namedt | ...
            crsp_msf.date > crsp_msf.nameendt;
crsp_msf(idxToDrop,:) = [];
crsp_msf.date = [];

% Check to see if we should only keep share codes 10 or 11 (domestic common
% equity)
if Params.domComEqFlag == 1
    idxToKeep = crsp_msf.shrcd==10 | crsp_msf.shrcd==11;
    crsp_msf  = crsp_msf(idxToKeep,:);
    fprintf('Removed %d observations from CRSP_MSF which didn''t have share codes 10 or 11.\n', sum(~idxToKeep));
end

% Check to keep only the sample specified in Params
idxToKeep = crsp_msf.dates >= (100*Params.SAMPLE_START + 1) & ...
            crsp_msf.dates <= (100*Params.SAMPLE_END + 12);
crsp_msf  = crsp_msf(idxToKeep,:);
fprintf('Removed %d observations from CRSP_MSF that were before the start date or after the end date specified in Params.\n',sum(~idxToKeep));

% Rename returns to indicate they are without delisting adjustment
crsp_msf.Properties.VariableNames{'ret'} = 'ret_x_dl';

% Choose variables to convert into matrices
varNames = {'shrcd','exchcd', 'siccd', 'prc', 'bid', 'ask', 'bidlo', ...
            'askhi', 'vol', 'ret_x_dl', 'shrout', 'cfacpr', 'cfacshr', ...
            'spread', 'retx'};
nVarNames = length(varNames);

% Save the link file for the COMPUSTAT matrices creation
crsp_link = crsp_msf(:,{'permno','dates'});
save([crspDirPath,'crsp_link.mat'],'crsp_link');

% Create & store the permno and dates vectors
permno = unique(crsp_msf.permno);
save([crspDirPath,'permno.mat'],'permno');

dates = unique(crsp_msf.dates);
save([crspDirPath,'dates.mat'],'dates');

clearvars -except Params varNames crsp_msf crspDirPath nVarNames

% Create & store the rest of the matrices
for i = 1:nVarNames
    % Store the name of the current variable
    thisVarName = char(varNames(i));
    
    % Timekeeping
    fprintf('Now working on variable %s, which is %d out of %d.\n', thisVarName, i, nVarNames);
    
    % Take only a table with permno, dates, and the current variable
    tempTable = crsp_msf(:,{'permno', 'dates', thisVarName}); 
    
    % Unstack the table - that creates the matrix we want
    unstackedTempTable = unstack(tempTable, thisVarName, 'dates'); 

    % Unstack keeps a column with the permnos
    unstackedTempTable.permno=[];
    
    % Convert the table to a matrix
    tempVar = table2array(unstackedTempTable)'; 
    
    % Store the variable by assigning to a temporary structure first
    tempStruct.(thisVarName) = tempVar;
    save([crspDirPath, thisVarName, '.mat'], ...
                                '-struct', 'tempStruct', thisVarName);
    
    % Timekeeping
    fprintf('Done with %s.\n', thisVarName);
    clear tempStruct 
end


fprintf('CRSP monthly variables run ended at %s.\n', char(datetime('now')));
