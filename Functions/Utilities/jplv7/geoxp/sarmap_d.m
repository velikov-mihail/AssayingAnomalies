% PURPOSE: An example using sarmap
%          to examine the sar models
%          by selecting sub-samples using a map
%---------------------------------------------------
% USAGE: sarmap_d
%---------------------------------------------------



load countyg.data;
y1 = countyg(:,4); % county employment growth rate
y2 = countyg(:,5); % county population growth rate

latt = countyg(:,2);
long = countyg(:,3);

[j W j] = xy2cont(-latt,-long);

n = length(y1);
countyg(:,16) = countyg(:,16)/1000;
xmat = [ones(n,1) countyg(:,8) countyg(:,10:end-1)];
xmat(:,2:end) = studentize(xmat(:,2:end));
vnames = strvcat('y=empgr80-90','constant','logy80','empdensity','popdensity','log area', ...
    'college','manufemp','unemploy','y-percapita','education spending','highway spending','police spending', ...
    'non-white','urban dummy');

sarmap(-latt,-long,xmat,y1*10,W,vnames);
