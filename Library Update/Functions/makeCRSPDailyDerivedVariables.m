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
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.


fprintf('\n\n\nNow working on creating some variables derived from daily CRSP. Run started at %s.\n',char(datetime('now')));

% Create daily market cap
% Make market capitalization
load dprc
load dshrout
dme = abs(dprc).*dshrout/1000;
dme(dme == 0) = nan;
save data/CRSP/daily/dme dme -v7.3
clear dprc dshrout dme


% Adjust for delisting
load dret_x_dl
load permno
load ddates
opts=detectImportOptions('Data/CRSP/daily/crsp_dsedelist.csv');
crsp_dsedelist=readtable('crsp_dsedelist.csv',opts);
crsp_dsedelist=crsp_dsedelist(ismember(crsp_dsedelist.permno,permno),:);
crsp_dsedelist(crsp_dsedelist.dlstcd==100,:)=[];
crsp_dsedelist.ddates=10000*year(crsp_dsedelist.dlstdt)+100*month(crsp_dsedelist.dlstdt)+day(crsp_dsedelist.dlstdt);
for i=1:height(crsp_dsedelist)
    c=find(permno==crsp_dsedelist.permno(i));
    r=find(isfinite(dret(:,c)),1,'last');
    if isfinite(r) & r<length(ddates)
        dret(r+1,c)=crsp_dsedelist.dlret(i); % Assumption is that we assign to the day after it last trades
    end
end
save data/CRSP/daily/dret dret -v7.3
clear dret permno ddates opts crsp_dsedelist i r c 


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

amihud=nan(size(ret));
years=unique(floor(dates/100));

dvol(dvol==0)=nan;
dvol=abs(dvol).*abs(dprc);

a=abs(dret)./dvol;
prc=abs(prc);

for i=1:length(years)
    indexYear=find(floor(ddates/10000)==years(i)); 
    indexLastMonth=find(floor(dates/100)==years(i),1,'last');
    b=a(indexYear,:);
    ind=(  sum( (b>=0),1)>200  )   &   prc(indexLastMonth,:)>5 ;
    b(:,~ind)=nan;    
    ind=(b>=0);
    temp=nansum(b,1)./sum(ind,1);
    r=find(dates==100*years(i)+12);
    amihud(r,:)=temp;
end
save data/amihud amihud
clear amihud dret dvol dates ret ddates prc years a i indexYear indexLastMonth b ind temp r 


% Now the monthly Amihud measure
load dret
load dvol
load dates
load ret
load ddates
load prc
load dprc

amihud=nan(size(ret));

dvol(dvol==0)=nan;
dvol=abs(dvol).*abs(dprc);

a=abs(dret)./dvol;
prc=abs(prc);

for i=12:size(ret,1)
    indexYear=find(floor(ddates/100)>=dates(i-11) & floor(ddates/100)<=dates(i));   
    b=a(indexYear,:);
    ind=(  sum( isfinite(b),1)>200     &   prc(i,:)>5 );
    b(:,~ind)=nan;    
    ind=isfinite(b);
    temp=nansum(b,1)./sum(ind,1);
    amihud(i,:)=temp;
end

save data/monthlyAmihud amihud
clear amihud dret dvol dates ret ddates prc years a i indexYear b ind temp r dprc 

% Make other measures from the daily data
load dates
load dret
load ddates
load ret
load dvol

% Realized volatilities
RVOL1 = nan(size(ret));
RVOL3 = nan(size(ret));
RVOL6 = nan(size(ret));
RVOL12 = nan(size(ret));
RVOL36 = nan(size(ret));
RVOL60 = nan(size(ret));

% Daily share volume at the monthly level
dshvol = nan(size(ret));
dshvolM = nan(size(ret));

% Max/min daily returns during the month
dretmax = nan(size(ret));
dretmin = nan(size(ret));


% Monthly loop range
FirstMonth=find(dates==floor(ddates(1)/100)); % Assumption is that the monthly data starts earlier than the daily data
LastMonth=length(dates);

for i = FirstMonth:LastMonth
    ind1=find(floor(ddates/100)==dates(i));
    ind3=find(floor(ddates/100)>=dates(max(i-2,1)) & floor(ddates/100)<=dates(i));
    ind6=find(floor(ddates/100)>=dates(max(i-2,1)) & floor(ddates/100)<=dates(i));
    ind12=find(floor(ddates/100)>=dates(max(i-2,1)) & floor(ddates/100)<=dates(i));
    ind36=find(floor(ddates/100)>=dates(max(i-2,1)) & floor(ddates/100)<=dates(i));
    ind60=find(floor(ddates/100)>=dates(max(i-2,1)) & floor(ddates/100)<=dates(i));
       
    RVOL1(i,:) = std(dret(ind1,:),0,1); % daily std
    RVOL3(i,:) = std(dret(ind3,:),0,1); % daily std
    RVOL6(i,:) = std(dret(ind6,:),0,1); % daily std
    RVOL12(i,:) = std(dret(ind12,:),0,1); % daily std
    RVOL36(i,:) = std(dret(ind36,:),0,1); % daily std
    RVOL60(i,:) = std(dret(ind60,:),0,1); % daily std

    dshvol(i,:) = sum(dvol(ind1,:),1); % sum of daily volume
    dshvolM(i,:) = max(dvol(ind1,:),[],1); % max of daily volume

    dretmax(i,:) = max(dvol(ind1,:),[],1); % max daily ret
    dretmin(i,:) = min(dvol(ind1,:),[],1); % min daily ret    
end
save data/RVOL1 RVOL1
save data/RVOL3 RVOL3
save data/RVOL6 RVOL6
save data/RVOL12 RVOL12
save data/RVOL36 RVOL36
save data/RVOL60 RVOL60
save data/dshvol dshvol
save data/dshvolM dshvolM
save data/dretmax dretmax
save data/dretmin dretmin
clear dretmax dretmin ind1 ind3 ind6 ind12 ind36 ind60 dates ddates dret i FirstMonth ret RVOL1 RVOL3 RVOL6 RVOL12 RVOL36 RVOL60 LastMonth dvol dshvol dshvolM

% Make IVOLs
load dates
load dret
load ddates
load ret
load dff

IVOL=nan(size(ret));
IVOL3=nan(size(ret));
dxret=dret-repmat(drf,1,size(ret,2));

% Monthly loop range
FirstMonth=find(dates==floor(ddates(1)/100)); % Assumption is that the monthly data starts earlier than the daily data
LastMonth=length(dates);

for i = FirstMonth:LastMonth
    ind1=find(floor(ddates/100)==dates(i));
    ind3=find(floor(ddates/100)>=dates(max(i-2,1)) & floor(ddates/100)<=dates(i));

    hor_ind=find(isfinite(sum(dxret(ind1,:),1)));
    for j=hor_ind
        res=nanols(dxret(ind1,j),[ones(size(dxret(ind1,j))) dmkt(ind1)]);
        IVOL(i,j) = sqrt(mean(res.resid.^2)); % ff residual
        res=nanols(dxret(ind3,j),[ones(size(dxret(ind3,j))) dmkt(ind3) dsmb(ind3) dhml(ind3)]);
        IVOL3(i,j) = sqrt(mean(res.resid.^2)); % ff residual
    end
end

save Data/IVOL IVOL
save Data/IVOL3 IVOL3
clear IVOL IVOL3 dxret FirstMonth LastMonth i ind1 ind3 hor_ind res j dates dret drf dmkt const dcma drmw dsmb dsmb2 dhml dff3 dff4 dff5 dff6 dffdates dumd

% Make CAR3s - or relegate to anomalies?
load rdq
load dates
load ddates
load dret
load dff
load ret
load nyse
load me

CAR3=nan(size(RDQ));

dxret=1+dret-repmat(dmkt+drf,1,size(dret,2)); % Add the rf to the mkt? Probably doesn't matter.
clear dret drf dmkt const dcma drmw dsmb dsmb2 dhml dff3 dff4 dff5 dff6 dffdates dumd eomflag

s=find(sum(isfinite(RDQ),2)>0,1,'first'); % First row with finite RDQ
e=length(dates);

for i=s:e
    ind=find(isfinite(RDQ(i,:)));
    for j=1:length(ind)
        c=ind(j);
        r=find(ddates==RDQ(i,c));
        if isfinite(r) & r<length(ddates)
            CAR3(i,c)=prod(dxret(r-1:r+1,c))-1;
        end
    end
end


CAR3=CAR3-1;
CAR3=FillMonths(CAR3);
CAR3(~isfinite(ret))=nan;

save Data/CAR3 CAR3

fprintf('CRSP daily derived variables run ended at %s.\n', char(datetime('now')));
