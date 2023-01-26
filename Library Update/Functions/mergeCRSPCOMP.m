function mergeCRSPCOMP(Params)
% PURPOSE: This function uses the stored tables from the COMPUSTAT annual and
% quarterly files to create matrices of dimensions number of months by number
% of stocks for all variables downloaded from COMPUSTAT
%------------------------------------------------------------------------------------------
% USAGE:   
% mergeCRSPCOMP(Params)              % Turns the COMPUSTAT files into matrices
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.domComEqFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.COMPVarNames - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.tcostsType - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% mergeCRSPCOMP(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses makeCOMPUSTATVariables()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on merging CRSP and annual COMPUSTAT. Run started at %s.\n',char(datetime('now')));

% Read the linking file
fileName = [Params.directory, filesep, 'Data', filesep, 'CRSP', filesep, 'crsp_ccmxpf_lnkhist.csv'];
opts       = detectImportOptions(fileName);
opts.VariableTypes(ismember(opts.VariableNames, {'gvkey'})) = {'char'};
crsp_ccmxpf_lnkhist = readtable(fileName, opts);

% Filter based on the CCM link
% Leave only link types LC or LU
idxToKeep = ismember(crsp_ccmxpf_lnkhist.linktype, {'LC','LU'});
crsp_ccmxpf_lnkhist = crsp_ccmxpf_lnkhist(idxToKeep, :);

% Leave the variables we need
crsp_ccmxpf_lnkhist = crsp_ccmxpf_lnkhist(:,{'lpermno','gvkey','linkdt','linkenddt'});

% Replace the missing linkeddt with the end of the sample
indNatEndDate = isnat(crsp_ccmxpf_lnkhist.linkenddt);
crsp_ccmxpf_lnkhist.linkenddt(indNatEndDate) = datetime(Params.SAMPLE_END, 12, 31);


% Load the annual COMPUSTAT file 
fileName = [Params.directory, filesep, 'Data', filesep, 'COMPUSTAT', filesep, 'comp_funda.csv'];
opts       = detectImportOptions(fileName);
opts.VariableTypes(ismember(opts.VariableNames, {'gvkey'})) = {'char'};
comp_funda = readtable(fileName, opts);

% Drop observations outside of our sample
idxToDrop = comp_funda.datadate > datetime(Params.SAMPLE_END, 12, 31) | ...
            comp_funda.datadate < datetime(Params.SAMPLE_START, 1, 1);
comp_funda(idxToDrop,:) = [];

% Merge & clean the COMPUSTAT annual file with CRSP Link history file
comp_funda_linked = outerjoin(comp_funda, crsp_ccmxpf_lnkhist, 'Type', 'Left', ...
                                                               'Keys', 'gvkey', ...
                                                               'MergeKeys', 1);

% Fiscal period end date must be within link date range 
idxToDrop = comp_funda_linked.datadate > comp_funda_linked.linkenddt |  ... 
            comp_funda_linked.datadate < comp_funda_linked.linkdt;
comp_funda_linked(idxToDrop,:) = [];  

% Must have permno
idxToDrop = isnan(comp_funda_linked.lpermno);
comp_funda_linked(idxToDrop,:)=[]; 

% Create the dates variable in yyyymm format - align a given fiscal year
% end with next year's June
comp_funda_linked.dates = 100*(1 + year(comp_funda_linked.datadate)) + 6; 

% Drop a few variables & chage name of permno column
comp_funda_linked(:,{'gvkey','linkdt','linkenddt'}) = []; 
comp_funda_linked.Properties.VariableNames{'lpermno'} = 'permno';

% Note: there are cases where a company changes its fiscal year end, which
% results in more than one observation per permno-year. See, e.g., year
% 1969 for permno 10006. We'll deal with those here by keeping only the  
% data from the fiscal year that happens later in the year
% Sort the table first
comp_funda_linked = sortrows(comp_funda_linked,{'permno','datadate'});

% Apply the anonymous function (i.e., leaving the last element) in the first argument to every variable, by grouping them by permno & dates
adj_comp_funda_linked = varfun(@(x) x(end), comp_funda_linked, 'GroupingVariables', {'permno','dates'}); 

% Count the number of permno-years with more than 1 row & print
nduplicates = sum(adj_comp_funda_linked.GroupCount > 1); 
fprintf('There were %d cases of permno-years in which companies moved their fiscal year end.\n', nduplicates); 

% Fix the names
varNames = adj_comp_funda_linked.Properties.VariableNames'; 
clndVarNames = regexprep(varNames,'Fun_','');
adj_comp_funda_linked.Properties.VariableNames = clndVarNames;

% Create the fiscal year end variable in yyyymmdd format and drop a couple
% of variables
adj_comp_funda_linked.FYE = 10000 * year(adj_comp_funda_linked.datadate) + ...
                              100 * month(adj_comp_funda_linked.datadate) + ...
                                    day(adj_comp_funda_linked.datadate);
adj_comp_funda_linked(:,{'GroupCount','datadate'}) = [];

% Create the individual variables
makeCOMPUSTATVariables(Params, adj_comp_funda_linked);

% Timekeeping
fprintf('CRSP and Annual COMPUSTAT merge ended at %s.\n', char(datetime('now')));

% Now do the quarterly COMPUSTAT variables 
% Timekeeping
fprintf('\n\n\nNow working on merging CRSP and quarterly COMPUSTAT. Run started at %s.\n', char(datetime('now')));

% Load the quarterly COMPUSTAT file 
fileName = [Params.directory, filesep, 'Data', filesep, 'COMPUSTAT', filesep, 'comp_fundq.csv'];
opts       = detectImportOptions(fileName);
opts.VariableTypes(ismember(opts.VariableNames, {'gvkey'})) = {'char'};
comp_fundq = readtable(fileName, opts);

% Drop observations with no RDQ or outside of our sample
idxToDrop = isnat(comp_fundq.rdq) | ...
            comp_fundq.datadate > datetime(Params.SAMPLE_END, 12, 31) | ...
            comp_fundq.datadate < datetime(Params.SAMPLE_START, 1, 1);
comp_fundq(idxToDrop,:)=[];

% Merge & clean the COMPUSTAT annual file with CRSP Link history file
comp_fundq_linked = outerjoin(comp_fundq, crsp_ccmxpf_lnkhist, 'Type', 'Left', ...
                                                               'Keys', 'gvkey', ...
                                                               'MergeKeys', 1);

% Fiscal period end date must be within link date range 
idxToDrop = comp_fundq_linked.datadate > comp_fundq_linked.linkenddt |  ... 
            comp_fundq_linked.datadate < comp_fundq_linked.linkdt;
comp_fundq_linked(idxToDrop,:) = [];  

% Must have permno
idxToDrop = isnan(comp_fundq_linked.lpermno);
comp_fundq_linked(idxToDrop,:) = []; 

% Create the dates variable in yyyymm format - assume available at the end
% of the RDQ month
comp_fundq_linked.dates = 100 * year(comp_fundq_linked.rdq) + ...
                                month(comp_fundq_linked.rdq); 

% Drop a few variables & chage name of permno column
comp_fundq_linked(:,{'gvkey','linkdt','linkenddt'}) = []; 
comp_fundq_linked.Properties.VariableNames{'lpermno'} = 'permno';

% Note: there are cases where multiple stock-quarter data points are
% associated with a single earnings announcement date (RDQ). These could be
% due to restatements, or delays in announcements. See, e.g., permno 63079
% announcements for 200708 in comp_fundq_linked:
% temp=comp_fundq_linked(comp_fundq_linked.permno==63079 & comp_fundq_linked.dates==200708,:);
% We'll deal with these by leaving the latest available fiscal quarter
% associated with each RDQ

% Sort the table first
comp_fundq_linked = sortrows(comp_fundq_linked, {'permno','rdq','datadate'});

% Apply the anonymous function (i.e., leaving the last element) in the first argument to every variable, by grouping them by permno & dates
adj_comp_fundq_linked = varfun(@(x) x(end,:), comp_fundq_linked, 'GroupingVariables', {'permno','dates'}); 

% Count the number of permno-quarters with more than 1 row & print
nduplicates = sum(adj_comp_fundq_linked.GroupCount > 1); 
fprintf('There were %d cases of permno-RDQ months associated with multiple quarters.\n', nduplicates); 

% Clean the names
varNames=adj_comp_fundq_linked.Properties.VariableNames'; 
clndVarNames=erase(varNames,'Fun_');
adj_comp_fundq_linked.Properties.VariableNames = clndVarNames;

% Create the RDQ and fiscal-quarter-end variables 
adj_comp_fundq_linked.RDQ  = 10000 * year(adj_comp_fundq_linked.rdq) + ...
                               100 * month(adj_comp_fundq_linked.rdq) + ...
                                     day(adj_comp_fundq_linked.rdq);
adj_comp_fundq_linked.FQTR = 10000 * year(adj_comp_fundq_linked.datadate) + ...
                               100 * month(adj_comp_fundq_linked.datadate) + ...
                                     day(adj_comp_fundq_linked.datadate);
adj_comp_fundq_linked(:,{'GroupCount','rdq','datadate'}) = [];

% Create the individual variables.The second argument tells it it's 
% quarterly variables
makeCOMPUSTATVariables(Params, adj_comp_fundq_linked, 1); 

% Timekeeping
fprintf('CRSP and Quarterly COMPUSTAT merge ended at %s.\n',char(datetime('now')));
