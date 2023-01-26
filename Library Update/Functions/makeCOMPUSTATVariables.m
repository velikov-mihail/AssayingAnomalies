function makeCOMPUSTATVariables(Params,comp_data,quarterlyIndicator)
% PURPOSE: This function uses the stored tables from the COMPUSTAT annual and
% quarterly files to create matrices of dimensions number of months by number
% of stocks for all variables downloaded from COMPUSTAT
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCOMPUSTATVariables(Params)              % Turns the COMPUSTAT files into matrices
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
%        -comp_data - a MATLAB table with columns including "permno", "dates", and 
%                       COMPUSTAT data to be stored in the number of months
%                       x number of stocks matrices
%        -quarterlyIndicator - a flag which when equal to 1 indicates that
%                       the function needs to construct data from the
%                       COMPUSTAT quarterly files
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% makeCOMPUSTATVariables(Params)              
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

% Store the COMPUSTAT directory path
compustatDirPath=[Params.directory,'Data/COMPUSTAT/'];

% Load a few variables
load permno
load dates
load ret

% Store a few constants
nStocks = length(permno);
nMonths = length(dates);
nObs = nStocks * nMonths;

% Create the linking table with CRSP
rptdDates = repmat(dates, 1, nStocks);
rptdPermno = repmat(permno', nMonths, 1);
crspMatLink = [reshape(rptdPermno, nObs, 1) ...
               reshape(rptdDates, nObs, 1)];
crspMatLinkTab = array2table(crspMatLink, 'VariableNames', {'permno', 'dates'});           

% Store the variable names & & drop the permno and dates
varNames = comp_data.Properties.VariableNames';
idxToDrop = ismember(varNames,{'permno','dates'});
varNames(idxToDrop) = [];

% Store the numer of variable names
nVarNames = length(varNames);

for i = 1:nVarNames
    % Store the current variable name & print for timekeeping
    thisVarName = char(varNames(i));   
    fprintf('Now working on COMPUSTAT variable %s, which is %d/%d.\n', upper(thisVarName), i, nVarNames);
    
    % Store the temporary table for this variable
    tempTab = comp_data(:,{'permno','dates',thisVarName});
    mergedTab = outerjoin(crspMatLinkTab, tempTab, 'Type', 'Left', ...
                                                   'MergeKeys', 1);
    % Unstack the table and turn it into a matrix
    thisVar = unstack(mergedTab, thisVarName, 'dates');
    thisVar.permno = [];
    thisVar = table2array(thisVar)';
    
    % If it's a quarterly COMPUSTAT variable, we need to fill in the months
    % in between the RDQ announcements. We'll only leave the FQTR variable
    % to have observations only during the announcement months
    if nargin==3
        if quarterlyIndicator == 1 && ~strcmp(thisVarName, 'FQTR')
            % Find all the columns with data
            stocksWithDataInd = find(sum(isfinite(thisVar),1) > 0);
            nStocksWithData = length(stocksWithDataInd);
            % Loop through them
            for j = 1:nStocksWithData
                % Store the current column/stock
                c = stocksWithDataInd(j);
                
                % Find the first and last rows
                firstR = find(isfinite(thisVar(:,c)), 1, 'first');
                lastR = find(isfinite(thisVar(:,c)), 1, 'last');
                
                % Loop throught the rows/months
                for r = firstR+1 : min(nMonths, lastR + 2)
                    if isnan(thisVar(r,c))
                        % Fill in the missing ones
                        thisVar(r, c) = thisVar(r-1, c);
                    end
                end
            end
        end
    end
    
    % Make sure the matrix is the same size as the return matrix
    if isequal(size(ret), size(thisVar))
        % Store the variable
        tempStruct.(upper(thisVarName)) = thisVar;
        fileName = [compustatDirPath, upper(thisVarName),'.mat'];
        save(fileName, '-struct', 'tempStruct', upper(thisVarName));
    else 
        error('COMPUSTAT variables wrong size.\n');
    end
    clear tempStruct
end
    