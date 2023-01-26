function makeCRSPDailyDerivedVariables(Params)
% PURPOSE: This function creates variables that are directly derived from the
% matrices created from the CRSP daily file
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCRSPDailyDerivedVariables(Params)              % Creates additional variables from the CRSP daily matrices
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
% makeCRSPDailyDerivedVariables(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Requires makeCRSPDailyData() to have been run.
%       Uses getFFDailyFactors()
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on creating some variables derived from daily CRSP. Run started at %s.\n',char(datetime('now')));


% Store the general and daily CRSP data path
dataPath = [Params.directory, 'Data/'];
dailyCRSPPath = [Params.directory, 'Data/CRSP/daily/'];

% Create daily market cap
% Make market capitalization
load dprc
load dshrout
dme = abs(dprc).*dshrout/1000;
dme(dme == 0) = nan;
save([dailyCRSPPath,'dme.mat'], 'dme', '-v7.3');
clearvars -except dataPath dailyCRSPPath Params


% Adjust for delisting
load dret_x_dl
load permno
load ddates

% Read the CRSP delist returns file
opts = detectImportOptions('Data/CRSP/daily/crsp_dsedelist.csv');
crsp_dsedelist = readtable('crsp_dsedelist.csv',opts);


% Drop the observations we don't need
idxToDrop = ~ismember(crsp_dsedelist.permno,permno) | ...
            crsp_dsedelist.dlstdt == max(crsp_dsedelist.dlstdt) | ...
            crsp_dsedelist.dlstcd == 100;
crsp_dsedelist(idxToDrop,:)=[];

% Turn the date into yyyymmdd format & drop the observations outside of
% sample
crsp_dsedelist.yyyymmdd = 10000 * year(crsp_dsedelist.dlstdt) + ...
                            100 * month(crsp_dsedelist.dlstdt) + ...
                                  day(crsp_dsedelist.dlstdt);
crsp_dsedelist(crsp_dsedelist.yyyymmdd > ddates(end),:) = [];

% Fill in the delisting returns
dret = dret_x_dl;
for i=1:height(crsp_dsedelist)

    % Find the column for this permno
    c = find(permno == crsp_dsedelist.permno(i));
    
    % Find the delisting day and the last day with a return observation   
    r_dt = find(ddates == crsp_dsedelist.yyyymmdd(i));
    r_last = find(isfinite(dret(:,c)), 1, 'last') + 1;
    
    
    % Choose where to assign the delisting return. If the return for this
    % permno (c) in the delisting day (r_dt) is NaN, and the previous
    % day return is finite, assign it to r_dt.
    if ~isempty(r_dt) && isnan(dret(r_dt,c)) && isfinite(dret(r_dt-1,c))
        r = r_dt;
    % Otherwise assign to the observation following the last non-NaN
    % observation we have for this permno
    elseif ~isempty(r_last) && r_last<length(ddates)
        r = r_last;
    else
        r = [];
    end
            
    if ~isempty(r)    
        dret(r+1,c) = crsp_dsedelist.dlret(i); 
    end
end
save([dailyCRSPPath,'dret.mat'],'dret','-v7.3');
clearvars -except dataPath dailyCRSPPath Params

% Download, clean up, and save the Fama-French Factors from Ken French's website
getFFDailyFactors(Params);

% Make Amihud - first the annual one
load dret
load dvol
load dates
load ret
load ddates
load prc
load dprc

% Initialize the matrix for the Amihud measure 
amihud = nan(size(ret));

% Remove zero-volume observations and calculate dollar volume
zeroVolInd = (dvol == 0);
dvol(zeroVolInd) = nan;
dvol = abs(dvol) .* abs(dprc);

% Calculate the daily price impact
priceImpact = abs(dret) ./ dvol;

% Take absolute value of the monthly price & store the number of months
prc = abs(prc);
nMonths = size(ret,1);

for i=12:nMonths
    % Find the days in the last year
    indexYear = (floor(ddates/100) >= dates(i-11) &  ...
                 floor(ddates/100) <= dates(i));   
    
    % Store last year's price impact
    lastYrPI = priceImpact(indexYear,:);
    
    % Apply the filters (200 obs & price>$5)
    idxToDrop= sum(isfinite(lastYrPI),1) < 200 | ...
                    prc(i,:) <= 5;
    lastYrPI(:,idxToDrop) = nan;    
    
    amihud(i,:) = mean(lastYrPI, 1, 'omitnan');
end
save([dataPath,'amihud.mat'],'amihud');
clearvars -except dataPath dailyCRSPPath Params

% Make other measures from the daily data
load dates
load dret
load ddates
load ret
load dvol

% Realized volatilities
RVOL1  = nan(size(ret));
RVOL3  = nan(size(ret));
RVOL6  = nan(size(ret));
RVOL12 = nan(size(ret));
RVOL36 = nan(size(ret));
RVOL60 = nan(size(ret));

% Daily share volume at the monthly level
dshvol  = nan(size(ret));
dshvolM = nan(size(ret));

% Max/min daily returns during the month
dretmax = nan(size(ret));
dretmin = nan(size(ret));

% Monthly loop range
FirstMonth = find(dates == floor(ddates(1)/100)); % Assumption is that the monthly data starts earlier than the daily data
LastMonth = length(dates);

for i = FirstMonth:LastMonth
    % Find the relevant days
    ind1  = (floor(ddates/100) == dates(i));
    ind3  = (floor(ddates/100) >= dates(max(i-2,1))  & floor(ddates/100) <= dates(i));
    ind6  = (floor(ddates/100) >= dates(max(i-5,1))  & floor(ddates/100) <= dates(i));
    ind12 = (floor(ddates/100) >= dates(max(i-11,1)) & floor(ddates/100) <= dates(i));
    ind36 = (floor(ddates/100) >= dates(max(i-35,1)) & floor(ddates/100) <= dates(i));
    ind60 = (floor(ddates/100) >= dates(max(i-59,1)) & floor(ddates/100) <= dates(i));
       
    % Calculate the volatility
    RVOL1(i,:)  = std(dret(ind1,:), 0, 1); 
    RVOL3(i,:)  = std(dret(ind3,:), 0, 1); 
    RVOL6(i,:)  = std(dret(ind6,:), 0, 1); 
    RVOL12(i,:) = std(dret(ind12,:), 0, 1); 
    RVOL36(i,:) = std(dret(ind36,:), 0, 1); 
    RVOL60(i,:) = std(dret(ind60,:), 0, 1); 
        
    % Calculate the monthly volume
    dshvol(i,:) = sum(dvol(ind1,:),1);     % sum of daily volume
    dshvolM(i,:) = max(dvol(ind1,:),[],1); % max of daily volume

    % Calculate the max/min daily returns
    dretmax(i,:) = max(dvol(ind1,:),[],1); % max daily ret
    dretmin(i,:) = min(dvol(ind1,:),[],1); % min daily ret    
end
save([dataPath,'RVOL1.mat'],'RVOL1');
save([dataPath,'RVOL3.mat'],'RVOL3');
save([dataPath,'RVOL6.mat'],'RVOL6');
save([dataPath,'RVOL12.mat'],'RVOL12');
save([dataPath,'RVOL36.mat'],'RVOL36');
save([dataPath,'RVOL60.mat'],'RVOL60');
save([dataPath,'dshvol.mat'],'dshvol');
save([dataPath,'dshvolM.mat'],'dshvolM');
save([dataPath,'dretmax.mat'],'dretmax');
save([dataPath,'dretmin.mat'],'dretmin');
clearvars -except dataPath dailyCRSPPath Params

% Make IVOLs
load dates
load dret
load ddates
load ret
load dff

% STore the number of stocks
nStocks = size(ret,2);

% Initialize the IVOL variables
IVOL  = nan(size(ret));
IVOL3 = nan(size(ret));
IffVOL  = nan(size(ret));
IffVOL3 = nan(size(ret));

% Create the daily excess returns
rptdRf = repmat(drf, 1, nStocks);
dxret  = dret - rptdRf;

% Monthly loop range
FirstMonth = find(dates == floor(ddates(1)/100)); % Assumption is that the monthly data starts earlier than the daily data
LastMonth  = length(dates);

for i = FirstMonth:LastMonth
    
    % Find the 1- and 3-month daily indices 
    ind1 = find(floor(ddates/100) == dates(i));
    ind3 = find(floor(ddates/100) >= dates(max(i-2,1)) & floor(ddates/100) <= dates(i));
    
    % Store the constant terms
    const1 = ones(length(ind1), 1);
    const3 = ones(length(ind3), 1);    
    
    % Find the stocks which we need to loop through
    hor_ind = find(isfinite(sum(dxret(ind1,:),1)));
    for j = hor_ind
        % CAPM 1-month residual
        res = nanols(dxret(ind1,j), [const1 dmkt(ind1)]);
        IVOL(i,j) = sqrt(mean(res.resid.^2)); 
        
        % FF3 1-month residual
        res = nanols(dxret(ind1,j), [const1 dmkt(ind1)  dsmb(ind1) dhml(ind1)]);
        IffVOL(i,j) = sqrt(mean(res.resid.^2)); 
        
         % CAPM 3-month residual
        res=nanols(dxret(ind3,j),[const3 dmkt(ind3)]);
        IVOL3(i,j) = sqrt(mean(res.resid.^2)); 
               
        % FF3 3-month residual
        res=nanols(dxret(ind3,j),[const3 dmkt(ind3) dsmb(ind3) dhml(ind3)]);
        IffVOL3(i,j) = sqrt(mean(res.resid.^2)); 
    end
end

% Store the IVOLs
save([dataPath,'IVOL.mat'],'IVOL');
save([dataPath,'IffVOL.mat'],'IffVOL');
save([dataPath,'IVOL3.mat'],'IVOL3');
save([dataPath,'IffVOL3.mat'],'IffVOL3');
clearvars -except dataPath dailyCRSPPath Params


% Make CAR3s - or relegate to anomalies?
load RDQ
load FQTR
load dates
load ddates
load dret
load dff
load ret
load nyse
load me

% Only leave the announcement dates
RDQ(isnan(FQTR)) = nan;

% Initialize the CAR3 matrix
CAR3 = nan(size(RDQ));

% Store the number of stocks
nStocks = size(dret,2);

% Calculate the abnormal return (ret_{i,t} - ret_{mkt,t})
rptdMkt = repmat(dmkt + drf, 1, nStocks);
dxret = 1 + dret - rptdMkt; 

% Monthly loop range
FirstMonth = find(sum(isfinite(RDQ),2)>0, 1, 'first'); % First row with finite RDQ
LastMonth  = length(dates);

% Loop over the months
for i = FirstMonth:LastMonth
    
    % Find all the announcements in the current month
    idxAnnouncements = find(isfinite(RDQ(i,:)));
    nAnnoncements = length(idxAnnouncements);
    
    % loop over the announcements
    for j = 1:nAnnoncements
        c = idxAnnouncements(j);
        r = find(ddates==RDQ(i,c));
        
        % Calculate the CAR3 if we found a match
        if ~isempty(r) && r < length(ddates)
            CAR3(i,c) = prod(dxret(r-1:r+1, c)) - 1;
        end
    end
end

% Fill the observations between quarters
CAR3 = FillMonths(CAR3);

% Remove all obseravtions where ret is nan
idxToDrop = isnan(ret);
CAR3(idxToDrop) = nan;

% Store the CAR3 variable
save([dataPath,'CAR3.mat'],'CAR3');

% Timekeeping
fprintf('CRSP daily derived variables run ended at %s.\n', char(datetime('now')));

