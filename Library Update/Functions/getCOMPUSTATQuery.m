function COMPUSTATQuery=getCOMPUSTATQuery(WRDS,Params,freq)
% PURPOSE: This function outputs a string with a query to be passed on to
% WRDS in order to download COMPUSTAT data.  
%------------------------------------------------------------------------------------------
% USAGE:   
% COMPUSTATQuery = getCOMPUSTATQuery(WRDS,Params,freq)    % Creates the query
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -WRDS - a WRDS connection object
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass     - WRDS password 
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END   - sample end dates
%             -Params.COMPUSTATVariablesFileName    - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%        -freq - a string indicating COMPUSTAT query to create. Can be 'annual' or 'quarterly'
%------------------------------------------------------------------------------------------
% Output:
%        -COMPUSTATQuery - a string with the specific query needed to
%                          download the COMPUSTAT annual or quarterly data
%------------------------------------------------------------------------------------------
% Examples:
%
% COMPUSTATAnnualQuery = getCOMPUSTATQuery(WRDS,Params,'annual');
% COMPUSTATQuarterlyQuery = getCOMPUSTATQuery(WRDS,Params,'quarterly');              
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

% First check if we want all COMPSUTAT variables
if strcmp(Params.COMPVarNames, 'All')
    if strcmp(freq,'annual')
        COMPUSTATQuery = 'select * from COMP.FUNDA where indfmt=''INDL'' and datafmt=''STD'' and consol=''C'' and popsrc=''D''';
    elseif strcmp(freq, 'quarterly')
        COMPUSTATQuery = 'select * from COMP.FUNDQ where indfmt=''INDL'' and datafmt=''STD'' and consol=''C'' and popsrc=''D''';        
    else
        error('Wrong freq parameter for COMPUSTAT query.\n');
    end
else
    % if not, we'll download the ones from the Excel file. Check if file exists
    if ~exist(Params.COMPVarNames, 'file')
        error('Wrong COMPUSTAT Variables File Name.\n');        
    end
    
    % Read the .csv with the variable names
    opts = detectImportOptions(Params.COMPVarNames);
    varNamesTable = readtable(Params.COMPVarNames, opts);
            
    % leave the correct column based on the COMPUSTAT update frequency (annual or quarterly)
    if strcmp(freq,'annual')
        varNames  = varNamesTable.Annual;
        tableName = 'funda';
        COMPUSTATQuery = ['select gvkey, datadate'];
    elseif strcmp(freq,'quarterly')
        varNames  = varNamesTable.Quarterly;
        tableName = 'fundq';
        COMPUSTATQuery = ['select gvkey, RDQ'];
    else
        error('Wrong freq parameter for COMPUSTAT query.\n');
    end
    
    % Clean it up
    varNames(strcmp(varNames,''), :) = [];
    varNames = lower(strtrim(varNames));
    
    % Get the variable names in the COMPUSTAT database & clean up
    compVarNamesQueryResult = fetch(WRDS, ['SELECT column_name FROM INFORMATION_SCHEMA.COLUMNS WHERE table_schema=''comp'' and table_name=''', tableName, '''']);
    compVarNames = lower(strtrim(compVarNamesQueryResult.column_name));
    
    % Make sure the names from the .csv file exist in the database
    [Lia, ~] = ismember(varNames,(compVarNames));
    if sum(1-Lia)>0
        fprintf('\nThe following variables are not on COMPUSTAT, so they will not be created:\n');
        ind = find(1-Lia==1);
        for i = 1:length(ind)
            fprintf('%s, ',char(varNames(ind(i))));
        end
        fprintf('\n');
        varNames(ind) = [];
    end
    
    % Add the varNames to the query
    nVarNames = length(varNames);
    for i = 1:nVarNames
        COMPUSTATQuery = [COMPUSTATQuery,', ',char(varNames(i))];
    end
    COMPUSTATQuery = [COMPUSTATQuery, ' from COMP.',tableName, ...
                     ' where indfmt=''INDL'' and datafmt=''STD'' and consol=''C'' and popsrc=''D'''];

end

