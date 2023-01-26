function makeCRSPDerivedVariables(Params)
% PURPOSE: This function creates variables that are directly derived from the
% matrices created from the CRSP monthly file
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCRSPDerivedVariables(Params)              % Creates additional variables from the CRSP monthly matrices
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
% makeCRSPDerivedVariables(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Requires makeCRSPMonthlyData() to have been run.
%       Uses makeIndustryClassifications(), getFFFactors(),
%       makeIndustryReturns(), makeUniverses(), mpp(), testCRSPData()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on making variables from CRSP. Run started at %s.\n\n', char(datetime('now')));

% Store the general data and CRSP paths
dataPath = [Params.directory, 'Data', filesep];
crspDirPath = [Params.directory, 'Data', filesep, 'CRSP', filesep];

% Adjust the returns for delisting
load ret_x_dl
load permno
load dates

% Read the CRSP delist returns file
opts = detectImportOptions([crspDirPath,'crsp_msedelist.csv']);
crsp_msedelist = readtable([crspDirPath,'crsp_msedelist.csv'],opts);

% Drop the observations we don't need 
idxToDrop = ~ismember(crsp_msedelist.permno,permno) | ...
            crsp_msedelist.dlstdt == max(crsp_msedelist.dlstdt);
crsp_msedelist(idxToDrop,:) = [];

% Turn the date into yyyymm format & drop the observations outside of
% sample
crsp_msedelist.yyyymm = 100 * year(crsp_msedelist.dlstdt) + ...
                              month(crsp_msedelist.dlstdt);
crsp_msedelist(crsp_msedelist.yyyymm > dates(end),:) = [];

% Fill in the delisting returns
ret = ret_x_dl;
for i = 1:height(crsp_msedelist)       
    % Find the column for this permno
    c = find(permno == crsp_msedelist.permno(i));
    
    % Find the delisting month and the last month with a return observation
    r_dt = find(dates == crsp_msedelist.yyyymm(i));
    r_last = find(isfinite(ret(:,c)),1,'last')+1;
    
    % Choose where to assign the delisting return. If the return for this
    % permno (c) in the delisting month (r_dt) is NaN, and the previous
    % month return is finite, assign it to r_dt.
    if ~isempty(r_dt) && isnan(ret(r_dt,c)) && isfinite(ret(r_dt-1,c))
        r = r_dt;
    % Otherwise assign to the observation following the last non-NaN
    % observation we have for this permno
    elseif ~isempty(r_last) && r_last<length(dates)
        r = r_last;
    else
        r=[];
    end
            
    if ~isempty(r)
        ret(r,c) = crsp_msedelist.dlret(i);        
    end
end


% Print out the Kodak delisting return
c = (permno == 11754);
r = find(dates == 201201);
fprintf('Adjusting for delisting complete. Kodak''s delisting return was %2.4f in %d\n',ret(r,c),dates(r));

% Save the retun matrix adjsuted for delisting
save([dataPath,'ret.mat'],'ret');
clearvars -except dataPath crspDirPath Params


% Adjust NASDAQ volume following Gao and Ritter (2010)
% See their Appendix B for more details
load dates
load exchcd
load vol_x_adj

% Adjust the volume
vol = vol_x_adj;

% Divide by 2 prior to 20010201
indToAdj = (exchcd == 3) & (dates < 200102); 
vol(indToAdj) = vol(indToAdj)/2;

% Divide by 1.8 for most of 2001:
indToAdj = (exchcd == 3)  & (dates >= 200102) & (dates < 200201); 
vol(indToAdj) = vol(indToAdj)/1.8;

% Divide by 1.6 for 2002 and 2003
indToAdj = (exchcd == 3) & (dates >= 200201) & (dates < 200401); 
vol(indToAdj) = vol(indToAdj)/1.6;

% Store the adjusted volume
save([crspDirPath,'vol.mat'],'vol');
clearvars -except dataPath crspDirPath Params

% Make market capitalization
load prc
load shrout
me = abs(prc).*shrout/1000;
me(me == 0) = nan;
save([dataPath,'me.mat'],'me');
clearvars -except dataPath crspDirPath Params

% Make dates for plotting
load dates
pdates = floor(dates/100) + mod(dates,100)/12;
save([dataPath,'pdates.mat'],'pdates');
clearvars -except dataPath crspDirPath Params

% Make the NYSE indicator variable
load exchcd
NYSE = (exchcd == 1)*1;
save([dataPath,'NYSE.mat'],'NYSE');
clearvars -except dataPath crspDirPath Params

% Download, clean up, and save the Fama-French Factors from Ken French's website
getFFFactors(Params);

% Rename the SIC code variable and create Fama/French industry variables 
makeIndustryClassifications(Params);

% Make & save the industry returns, based on FF49 classification
load FF49
[iFF49ret, iFF49reta] = makeIndustryReturns(FF49);
save([dataPath,'iFF49ret.mat'],'iFF49ret');
save([dataPath,'iFF49reta.mat'],'iFF49reta');
clearvars -except dataPath crspDirPath Params

% Make different universes
makeUniverses(Params);

% Make Share Issuance Variables
load shrout
load cfacshr
ashrout = shrout.*cfacshr;
dashrout = log(ashrout./lag(ashrout,12,nan)); % percent change in split adjusted shares outstanding
save([dataPath,'ashrout.mat'],'ashrout');
save([dataPath,'dashrout.mat'],'dashrout');
clearvars -except dataPath crspDirPath Params

% Make Momentum variables
load ret
R     = makePastPerformance(ret, 12, 1);                                   % "R" = gross returns (past perfromance)-- cumulates returns (gross) from 12 month ago to one month ago (NOT including last month)
R62   = makePastPerformance(ret, 6,  1);                                   % Cumulates gross returns from 6 month ago to 1 month ago ("recent horizon past perfromance")
R127  = makePastPerformance(ret, 12, 6);                                   % Cumulates gross returns from 12 month ago to 6 months ago ("intermediate horizon past perfromance")
R3613 = makePastPerformance(ret, 36, 12);                                  % Cumulates gross returns from 36 month ago to 12 months ago (for DeBont and Thaler long run reversals)

save([dataPath, 'R.mat'], 'R'); 
save([dataPath, 'R62.mat'], 'R62');
save([dataPath, 'R127.mat'], 'R127');
save([dataPath, 'R3613.mat'], 'R3613');
clearvars -except dataPath crspDirPath Params

% Test that your data matches up with some reference data 
testCRSPData();

% Timekeeping
fprintf('CRSP monthly derived variables run ended at %s.\n', char(datetime('now')));
